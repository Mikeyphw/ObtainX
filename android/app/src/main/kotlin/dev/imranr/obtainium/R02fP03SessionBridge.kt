package dev.imranr.obtainium

import android.app.Activity
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInstaller
import android.content.pm.PackageManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import io.flutter.plugin.common.BinaryMessenger
import io.flutter.plugin.common.MethodChannel
import java.io.File
import java.io.FileInputStream
import java.security.MessageDigest
import java.util.UUID
import java.util.concurrent.Executors
import org.json.JSONObject
import org.json.JSONArray

/**
 * R02F P03: first-party, owned, cancellable Android PackageInstaller session.
 * Unlike the legacy plugin, the session ID is known before commit. No private
 * installer APIs, root permissions, or shell commands are used.
 *
 * A successful abandon is NOT proof that a previously installed APK's bytes
 * are unchanged. An independent package observation is required; uncertainty
 * is reported as UNKNOWN, never SUCCESS or CANCELLED.
 */
internal class R02fP03SessionBridge(
    private val activity: Activity,
    messenger: BinaryMessenger,
) {
    private val app = activity.applicationContext
    private val installer = app.packageManager.packageInstaller
    private val prefs = app.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
    private val mainHandler = Handler(Looper.getMainLooper())
    private val worker = Executors.newSingleThreadExecutor()
    private val guard = Any()
    private var current: Operation? = restore()

    private data class Operation(
        val id: String,
        val listingKey: String,
        val packageName: String,
        val sessionId: Int,
        val baseline: String,
        var state: String = "staged",
        var cancelRequested: Boolean = false,
        var waiter: MethodChannel.Result? = null,
    ) {
        fun toJson() = JSONObject().apply {
            put("id", id)
            put("listingKey", listingKey)
            put("packageName", packageName)
            put("sessionId", sessionId)
            put("baseline", baseline)
            put("state", state)
            put("cancelRequested", cancelRequested)
        }
    }

    init {
        live = this
        MethodChannel(messenger, CHANNEL).setMethodCallHandler { call, reply ->
            when (call.method) {
                "stage" -> {
                    val paths = call.argument<List<String>>("paths")
                    val pkg = call.argument<String>("packageName")
                    val listing = call.argument<String>("listingKey")
                    if (pkg.isNullOrBlank() || listing.isNullOrBlank() || paths.isNullOrEmpty()) {
                        reply.error("BAD_ARGUMENTS", "Missing package/listing/APK files", null)
                    } else {
                        worker.execute { stage(pkg, listing, paths, reply) }
                    }
                }
                "commit" -> {
                    val id = call.argument<String>("id")
                    worker.execute { commit(id, reply) }
                }
                "cancel" -> {
                    val id = call.argument<String>("id")
                    worker.execute { cancel(id, reply) }
                }
                "pending" -> {
                    worker.execute {
                        try {
                            val op = synchronized(guard) { current }
                            val pending = op?.let { operation ->
                                operation.toJson().apply {
                                    put("sessionExists", installer.getSessionInfo(operation.sessionId) != null)
                                }.toString()
                            }
                            answer(reply, mapOf("active" to pending,
                                "terminal" to prefs.getString("terminal", null),
                                "orphanStatus" to prefs.getString("orphanStatus", null)))
                        } catch (ex: Exception) {
                            error(reply, "P03_PENDING_UNKNOWN", ex.message)
                        }
                    }
                }
                else -> reply.notImplemented()
            }
        }
        worker.execute { reconcileAfterRestart() }
    }

    private fun answer(reply: MethodChannel.Result, value: Any?) {
        mainHandler.post { reply.success(value) }
    }

    private fun error(reply: MethodChannel.Result, code: String, detail: String?) {
        mainHandler.post { reply.error(code, detail ?: code, null) }
    }

    private fun restore(): Operation? {
        val json = prefs.getString("active", null) ?: return null
        return try {
            val v = JSONObject(json)
            Operation(
                v.getString("id"), v.getString("listingKey"), v.getString("packageName"),
                v.getInt("sessionId"), v.getString("baseline"),
                v.getString("state"), v.optBoolean("cancelRequested", false),
            )
        } catch (_: Exception) {
            // Corrupt state is never treated as an abandoned or installed session.
            prefs.edit().putString("terminal", "CORRUPT_JOURNAL_UNKNOWN").remove("active").commit()
            null
        }
    }

    private fun persist(op: Operation): Boolean = prefs.edit()
        .putString("active", op.toJson().toString()).commit()

    private fun sha256(file: File): String? {
        if (!file.isFile || !file.canRead()) return null
        return try {
            val digest = MessageDigest.getInstance("SHA-256")
            FileInputStream(file).use { input ->
                val buffer = ByteArray(32768)
                while (true) {
                    val bytes = input.read(buffer)
                    if (bytes < 0) break
                    digest.update(buffer, 0, bytes)
                }
            }
            digest.digest().joinToString("") { "%02x".format(it) }
        } catch (_: Exception) { null }
    }

    private fun fingerprint(pkg: String): String {
        return try {
            @Suppress("DEPRECATION")
            val info = app.packageManager.getPackageInfo(pkg, 0)
            val source = info.applicationInfo?.sourceDir?.let { sha256(File(it)) }
            // Preserve ALL original split APK byte hashes, not just base.apk.
            // Hash-order is stable even when PackageManager changes install dirs.
            val splitHashes = (info.applicationInfo?.splitSourceDirs?.toList() ?: emptyList())
                .map { sha256(File(it)) ?: "" }.sorted()
            JSONObject().apply {
                put("present", true)
                put("versionCode", if (Build.VERSION.SDK_INT >= 28) info.longVersionCode else info.versionCode.toLong())
                put("versionName", info.versionName ?: "")
                put("lastUpdateTime", info.lastUpdateTime)
                put("baseSha256", source ?: JSONObject.NULL)
                put("splitSha256", JSONArray(splitHashes))
            }.toString()
        } catch (_: PackageManager.NameNotFoundException) {
            JSONObject().put("present", false).toString()
        }
    }

    private fun baselineStillProven(op: Operation): Boolean {
        val before = JSONObject(op.baseline)
        val after = JSONObject(fingerprint(op.packageName))
        if (before.optBoolean("present") != after.optBoolean("present")) return false
        if (!before.optBoolean("present")) return true
        // A matching version alone is NOT enough: require both APK fingerprints.
        val a = before.optString("baseSha256", "")
        val b = after.optString("baseSha256", "")
        val oldSplits = before.optJSONArray("splitSha256") ?: return false
        val newSplits = after.optJSONArray("splitSha256") ?: return false
        if (oldSplits.length() != newSplits.length()) return false
        for (i in 0 until oldSplits.length()) {
            val oldSha = oldSplits.optString(i, "")
            if (oldSha.length != 64 || oldSha != newSplits.optString(i, "")) return false
        }
        return a.length == 64 && a == b &&
            before.optLong("versionCode", -1) == after.optLong("versionCode", -2) &&
            before.optString("versionName") == after.optString("versionName") &&
            before.optLong("lastUpdateTime", -1) == after.optLong("lastUpdateTime", -2)
    }

    private fun stage(pkg: String, listingKey: String, paths: List<String>, reply: MethodChannel.Result) {
        var sessionId = -1
        try {
            synchronized(guard) {
                if (current != null) throw IllegalStateException("INSTALL_ALREADY_ACTIVE")
            }
            val members = paths.map { File(it) }
            if (members.any { !it.isFile || !it.canRead() || it.length() <= 0L }) {
                throw IllegalArgumentException("Missing or unreadable APK input")
            }
            if (members.distinctBy { it.name }.size != members.size ||
                members.any { !it.name.lowercase().endsWith(".apk") }) {
                throw IllegalArgumentException("Invalid/duplicate APK session members")
            }
            val total = members.sumOf { it.length() }
            if (total <= 0L || total > 1024L * 1024L * 1024L) {
                throw IllegalArgumentException("Unbounded APK session size")
            }
            val params = PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL)
            params.setAppPackageName(pkg)
            params.setSize(total)
            if (Build.VERSION.SDK_INT >= 31) {
                params.setRequireUserAction(PackageInstaller.SessionParams.USER_ACTION_REQUIRED)
            }
            sessionId = installer.createSession(params)
            val baseline = fingerprint(pkg)
            val observed = JSONObject(baseline)
            if (observed.optBoolean("present", false)) {
                val baseHash = observed.optString("baseSha256", "")
                val splits = observed.optJSONArray("splitSha256")
                if (baseHash.length != 64 || splits == null ||
                    (0 until splits.length()).any { splits.optString(it, "").length != 64 }) {
                    throw IllegalStateException("ORIGINAL_APK_BYTES_UNREADABLE")
                }
            }
            val op = Operation(UUID.randomUUID().toString(), listingKey, pkg, sessionId, baseline)
            synchronized(guard) {
                if (current != null || !persist(op)) throw IllegalStateException("JOURNAL_WRITE_REFUSED")
                current = op
            }
            installer.openSession(sessionId).use { session ->
                for (apk in members) {
                    session.openWrite(apk.name, 0L, apk.length()).use { output ->
                        FileInputStream(apk).use { input -> input.copyTo(output, 32768) }
                        session.fsync(output)
                    }
                }
            }
            answer(reply, mapOf("id" to op.id, "sessionId" to sessionId, "state" to "staged"))
        } catch (ex: Exception) {
            if (sessionId > 0) {
                try { installer.abandonSession(sessionId) } catch (_: Exception) { }
            }
            synchronized(guard) {
                val matching = current?.sessionId == sessionId
                if (matching) {
                    current = null
                    prefs.edit().remove("active").putString("terminal", "STAGING_FAILED_UNKNOWN").commit()
                }
            }
            error(reply, "P03_STAGE_REFUSED", ex.message)
        }
    }

    private fun commit(id: String?, reply: MethodChannel.Result) {
        val op = synchronized(guard) { current?.takeIf { it.id == id } }
        if (op == null) { error(reply, "STALE_OWNER", "Session is not active"); return }
        synchronized(guard) {
            if (op.state != "staged" || op.cancelRequested || op.waiter != null) {
                error(reply, "STATE_REFUSED", "Session was already dispatched or cancelled")
                return
            }
            op.state = "committing"
            if (!persist(op)) {
                op.state = "staged"
                error(reply, "JOURNAL_WRITE_REFUSED", null)
                return
            }
            op.waiter = reply
        }
        try {
            val intent = Intent(app, R02fP03ResultReceiver::class.java).apply {
                action = ACTION
                putExtra("operationId", op.id)
                putExtra("sessionId", op.sessionId)
            }
            val flags = PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_MUTABLE
            val callback = PendingIntent.getBroadcast(app, op.sessionId, intent, flags)
            installer.openSession(op.sessionId).use { session ->
                session.commit(callback.intentSender)
            }
        } catch (ex: Exception) {
            // A failed commit can still have reached PackageManager. Do not
            // report cancelled or restore an APK on this error path.
            finish(op, "unknown", ex.message)
        }
    }

    private fun cancel(id: String?, reply: MethodChannel.Result) {
        val op = synchronized(guard) { current?.takeIf { it.id == id } }
        if (op == null) {
            answer(reply, mapOf("status" to "refused", "reason" to "stale_or_finished"))
            return
        }
        synchronized(guard) {
            op.cancelRequested = true
            if (!persist(op)) {
                answer(reply, mapOf("status" to "unknown", "reason" to "journal_write_failed"))
                return
            }
        }
        var abandoned = false
        try {
            installer.abandonSession(op.sessionId)
            abandoned = installer.getSessionInfo(op.sessionId) == null
        } catch (_: Exception) { /* Session may have crossed the commit boundary. */ }
        // The session may have crossed commit before a cancellation request.
        // Never advertise rollback from a state whose commit result was not
        // observed. A second device observation catches delayed package writes.
        val cancellationWindow = op.state == "approval" || op.state == "staged"
        val unchangedBeforeSettle = try { baselineStillProven(op) } catch (_: Exception) { false }
        if (abandoned && unchangedBeforeSettle) {
            try { Thread.sleep(600L) } catch (_: InterruptedException) {
                Thread.currentThread().interrupt()
            }
        }
        val stillAbsent = try { installer.getSessionInfo(op.sessionId) == null } catch (_: Exception) { false }
        val unchanged = unchangedBeforeSettle &&
            try { baselineStillProven(op) } catch (_: Exception) { false }
        val outcome = if (abandoned && stillAbsent && unchanged && cancellationWindow) {
            "cancelled"
        } else "unknown"
        if (outcome == "cancelled" || abandoned) {
            finish(op, outcome, if (outcome == "unknown") "BASELINE_UNVERIFIED" else null)
        } else {
            // A sealed session may still be applying an APK. Keep its journal
            // and callback alive rather than manufacture a terminal rollback.
            synchronized(guard) {
                if (current?.id == op.id) {
                    op.state = "cancel_uncertain"
                    persist(op)
                }
            }
        }
        answer(reply, mapOf("status" to outcome, "sessionAbandoned" to abandoned,
            "baselineBytesVerified" to unchanged))
    }

    private fun finish(op: Operation, outcome: String, detail: String?) {
        val waiter: MethodChannel.Result?
        synchronized(guard) {
            if (current?.id != op.id) return
            waiter = op.waiter
            op.waiter = null
            current = null
            val terminal = JSONObject().apply {
                put("id", op.id)
                put("listingKey", op.listingKey)
                put("packageName", op.packageName)
                put("sessionId", op.sessionId)
                put("outcome", outcome)
                put("detail", detail ?: "")
                put("baseline", op.baseline)
                put("after", fingerprint(op.packageName))
            }
            prefs.edit().putString("terminal", terminal.toString()).remove("active").commit()
        }
        if (waiter != null) answer(waiter, mapOf("outcome" to outcome, "detail" to (detail ?: "")))
    }

    private fun reconcileAfterRestart() {
        val op = synchronized(guard) { current } ?: return
        val orphan = prefs.getString("orphanStatus", null)?.let { text ->
            try { JSONObject(text) } catch (_: Exception) { null }
        }
        if (orphan != null && orphan.optString("id") == op.id &&
            orphan.optInt("sessionId", -1) == op.sessionId) {
            // A callback can arrive after Flutter detached. Consume it once;
            // a terminal Android status is not proof of the planned APK bytes.
            prefs.edit().remove("orphanStatus").commit()
            val androidStatus = orphan.optInt("status", -999)
            if (androidStatus == PackageInstaller.STATUS_PENDING_USER_ACTION) {
                synchronized(guard) {
                    op.state = "approval"
                    persist(op)
                }
            } else {
                finish(op, "unknown", "RESTART_ORPHAN_ANDROID_STATUS_$androidStatus")
                return
            }
        }
        val stillOwned = try { installer.getSessionInfo(op.sessionId) != null }
            catch (_: Exception) { false }
        if (op.cancelRequested && stillOwned) {
            cancel(op.id, object : MethodChannel.Result {
                override fun success(result: Any?) { }
                override fun error(errorCode: String, errorMessage: String?, errorDetails: Any?) { }
                override fun notImplemented() { }
            })
        } else if (!stillOwned) {
            // Do not fabricate a successful install or a rollback on restart.
            finish(op, "unknown", "RESTART_SESSION_FINALIZED_UNOBSERVED")
        }
    }

    private fun onStatus(intent: Intent) {
        val id = intent.getStringExtra("operationId") ?: return
        val sessionId = intent.getIntExtra("sessionId", -1)
        val op = synchronized(guard) { current?.takeIf { it.id == id && it.sessionId == sessionId } }
            ?: return
        val status = intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE)
        if (status == PackageInstaller.STATUS_PENDING_USER_ACTION) {
            synchronized(guard) {
                if (op.cancelRequested) return
                op.state = "approval"
                if (!persist(op)) return
            }
            try {
                @Suppress("DEPRECATION")
                val approval = if (Build.VERSION.SDK_INT >= 33) {
                    intent.getParcelableExtra(Intent.EXTRA_INTENT, Intent::class.java)
                } else {
                    intent.getParcelableExtra(Intent.EXTRA_INTENT) as? Intent
                }
                if (approval != null) {
                    activity.startActivity(approval.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                }
            } catch (_: Exception) {
                // The pending session remains visible through pending(). A
                // later foreground UI can cancel rather than assume success.
            }
            return
        }
        // Never hash installed APKs on Android's main thread. PackageManager
        // status alone is insufficient to prove the planned APK was installed.
        // The worker performs the expensive observation and durably journals it.
        try {
            worker.execute {
                val outcome = if (status == PackageInstaller.STATUS_SUCCESS &&
                    try { !baselineStillProven(op) } catch (_: Exception) { false }) {
                    "success"
                } else if (op.cancelRequested || status == PackageInstaller.STATUS_SUCCESS) {
                    "unknown"
                } else {
                    "error"
                }
                finish(op, outcome, "ANDROID_STATUS_$status")
            }
        } catch (_: java.util.concurrent.RejectedExecutionException) {
            app.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
                .putString("orphanStatus", JSONObject().apply {
                    put("id", op.id)
                    put("sessionId", op.sessionId)
                    put("status", status)
                }.toString()).commit()
        }
    }

    fun detach() {
        if (live === this) live = null
        synchronized(guard) {
            // Dart's old engine will no longer receive completion. The durable
            // native session remains and is re-attached on next activity start.
            current?.waiter = null
        }
        worker.shutdown()
    }

    companion object {
        const val CHANNEL = "dev.imranr.obtainium/r02f_p03_session"
        const val ACTION = "dev.imranr.obtainium.R02F_P03_SESSION_RESULT"
        const val PREFS = "obtainx_r02f_p03_sessions"
        @Volatile private var live: R02fP03SessionBridge? = null

        fun receive(context: Context, intent: Intent) {
            val instance = live
            if (instance != null) {
                instance.mainHandler.post { instance.onStatus(intent) }
            } else {
                // The activity may have died while Android delivered the
                // terminal status. Preserve evidence, never fabricate PASS.
                context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
                    .putString("orphanStatus", JSONObject().apply {
                        put("id", intent.getStringExtra("operationId") ?: "")
                        put("sessionId", intent.getIntExtra("sessionId", -1))
                        put("status", intent.getIntExtra(PackageInstaller.EXTRA_STATUS, -999))
                    }.toString()).commit()
            }
        }
    }
}

/** Explicit, app-private receiver survives Flutter route/activity recreation. */
class R02fP03ResultReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == R02fP03SessionBridge.ACTION) {
            R02fP03SessionBridge.receive(context, intent)
        }
    }
}
