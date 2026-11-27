package dev.imranr.obtainium

import android.content.Context
import android.net.Uri
import android.os.Handler
import android.os.Build
import android.content.pm.PackageManager
import android.os.Looper
import android.provider.OpenableColumns
import io.flutter.plugin.common.BinaryMessenger
import io.flutter.plugin.common.MethodChannel
import java.io.File
import java.io.FileOutputStream
import java.security.MessageDigest
import java.util.Locale
import java.util.UUID
import java.util.concurrent.Executors
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicBoolean

/** R02: SAF-only, bounded, cancellable import to app-private temporary storage.
 * No install privilege, no filesystem path supplied by a document provider,
 * no persistent grants, and no Android package mutation in this bridge.
 */
internal class R02LocalArchiveBridge(
    private val context: Context,
    messenger: BinaryMessenger,
) {
    private val worker = Executors.newSingleThreadExecutor()
    private val main = Handler(Looper.getMainLooper())
    private val cancelled = ConcurrentHashMap<String, AtomicBoolean>()
    private val staging: File = File(context.cacheDir, "r02-local-import")
    private val channel = MethodChannel(messenger, "dev.imranr.obtainium/r02_local_archive")

    companion object {
        private const val LIMIT_BYTES = 1024L * 1024L * 1024L
        private const val STORAGE_RESERVE_BYTES = 16L * 1024L * 1024L
        private val TOKEN = Regex("^[A-Za-z0-9_-]{8,80}$")
        private val FILE = Regex("^r02-[0-9a-f-]{36}\\.(?:apk|apks|apkm|xapk|zip|tar|tgz|tar\\.gz|tar\\.bz2|tar\\.xz)$")
        private val SUFFIXES = listOf(".tar.gz", ".tar.bz2", ".tar.xz", ".apks", ".apkm", ".xapk", ".apk", ".zip", ".tar", ".tgz")
    }

    init {
        channel.setMethodCallHandler { call, reply ->
            when (call.method) {
                "availableBytes" -> {
                    val path = call.argument<String>("directory")
                    val bytes = runCatching {
                        require(!path.isNullOrBlank())
                        val directory = File(requireNotNull(path)).canonicalFile
                        require(directory.isDirectory)
                        directory.usableSpace
                    }.getOrNull()
                    if (bytes == null || bytes <= 0L) reply.error("R02_STORAGE_UNAVAILABLE", "Storage capacity unavailable", null)
                    else reply.success(bytes)
                }
                "copy" -> {
                    val uri = call.argument<String>("uri")
                    val id = call.argument<String>("id")
                    if (uri == null || id == null || !TOKEN.matches(id) || cancelled.containsKey(id)) {
                        reply.error("R02_INVALID_REQUEST", "Invalid or duplicate document request", null)
                        return@setMethodCallHandler
                    }
                    val flag = AtomicBoolean(false)
                    cancelled[id] = flag
                    worker.execute {
                        try {
                            val result = copyDocument(uri, flag)
                            main.post { reply.success(result) }
                        } catch (e: Exception) {
                            main.post { reply.error("R02_COPY_REFUSED", e.message ?: "Document copy refused", null) }
                        } finally {
                            cancelled.remove(id, flag)
                        }
                    }
                }
                "cancel" -> {
                    val id = call.argument<String>("id")
                    reply.success(id != null && cancelled[id]?.let { it.set(true); true } == true)
                }
                "sourceEvidence" -> {
                    val target = call.argument<String>("package")
                    val version = call.argument<Number>("version")
                    val sources = call.argument<List<String>>("sources")
                    if (target.isNullOrBlank() || version == null || sources.isNullOrEmpty()) {
                        reply.error("R02_EVIDENCE_ARGS", "Missing exact source APK claim", null)
                    } else {
                        worker.execute {
                            val evidence = runCatching {
                                sourceEvidence(target, version.toLong(), sources)
                            }.getOrNull()
                            main.post {
                                if (evidence == null) reply.error("R02_EVIDENCE_REFUSED", "APK identity/signing unavailable", null)
                                else reply.success(evidence)
                            }
                        }
                    }
                }
                "installedEvidence" -> {
                    val target = call.argument<String>("package")
                    if (target.isNullOrBlank()) {
                        reply.error("R02_VERIFY_ARGS", "Missing package identity", null)
                    } else {
                        worker.execute {
                            val evidence = runCatching { installedEvidence(target) }.getOrNull()
                            main.post { reply.success(evidence) }
                        }
                    }
                }
                "verifyInstalled" -> {
                    val target = call.argument<String>("package")
                    val version = call.argument<Number>("version")
                    val hashes = call.argument<List<String>>("hashes")
                    val signers = call.argument<List<String>>("signers")
                    if (target.isNullOrBlank() || version == null || hashes.isNullOrEmpty() || signers.isNullOrEmpty()) {
                        reply.error("R02_VERIFY_ARGS", "Missing exact installed-package claim", null)
                    } else {
                        worker.execute {
                            val verified = runCatching {
                                verifyInstalled(target, version.toLong(), hashes, signers)
                            }.getOrDefault(false)
                            main.post { reply.success(verified) }
                        }
                    }
                }
                "dispose" -> {
                    val path = call.argument<String>("path")
                    if (path == null) {
                        reply.error("R02_INVALID_PATH", "Missing temporary file", null)
                    } else {
                        reply.success(dispose(path))
                    }
                }
                else -> reply.notImplemented()
            }
        }
    }

    fun close() {
        channel.setMethodCallHandler(null)
        cancelled.values.forEach { it.set(true) }
        worker.shutdownNow()
    }

    private fun selectedName(uri: Uri): String {
        context.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
            if (cursor.moveToFirst()) {
                val idx = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                if (idx >= 0) return cursor.getString(idx) ?: ""
            }
        }
        throw IllegalArgumentException("Document display name missing; cannot determine archive format")
    }

    private fun copyDocument(raw: String, cancel: AtomicBoolean): Map<String, Any> {
        val uri = Uri.parse(raw)
        require(uri.scheme == "content" && !uri.authority.isNullOrBlank() && uri.fragment == null) {
            "A real SAF content URI is required"
        }
        val display = selectedName(uri)
        require(display.length in 1..255 && !display.contains('/') && !display.contains('\\') &&
                !display.contains('\u0000') && !display.contains("..")) { "Unsafe document name" }
        val suffix = SUFFIXES.firstOrNull { display.lowercase(Locale.ROOT).endsWith(it) }
            ?: throw IllegalArgumentException("Unsupported install artifact format")
        require(staging.isDirectory || staging.mkdirs()) { "Private import cache unavailable" }
        require(!java.nio.file.Files.isSymbolicLink(staging.toPath())) { "Unsafe import cache directory" }
        val id = UUID.randomUUID().toString()
        val pending = File(staging, "r02-$id.pending")
        val ready = File(staging, "r02-$id$suffix")
        val md = MessageDigest.getInstance("SHA-256")
        var bytes = 0L
        var capacityCheckedAt = -1024L * 1024L
        val started = android.os.SystemClock.elapsedRealtime()
        try {
            val input = context.contentResolver.openInputStream(uri)
                ?: throw IllegalArgumentException("Document content could not be opened")
            input.use { source ->
                FileOutputStream(pending, false).use { target ->
                    val buffer = ByteArray(64 * 1024)
                    while (true) {
                        if (cancel.get()) throw IllegalStateException("User cancelled import")
                        require(android.os.SystemClock.elapsedRealtime() - started < 300_000L) { "Import deadline exceeded" }
                        if (bytes - capacityCheckedAt >= 1024L * 1024L) {
                            require(staging.usableSpace >= STORAGE_RESERVE_BYTES + 2L * 1024L * 1024L) { "Insufficient private import storage" }
                            capacityCheckedAt = bytes
                        }
                        val n = source.read(buffer)
                        if (n < 0) break
                        if (n == 0) continue
                        if (n.toLong() > LIMIT_BYTES - bytes) throw IllegalArgumentException("Archive exceeds 1GiB limit")
                        target.write(buffer, 0, n)
                        md.update(buffer, 0, n)
                        bytes += n
                    }
                    target.fd.sync()
                }
            }
            if (cancel.get()) throw IllegalStateException("User cancelled import")
            require(bytes > 0L) { "Empty install artifact" }
            require(pending.renameTo(ready)) { "Atomic import staging failed" }
            val digest = md.digest().joinToString("") { "%02x".format(it.toInt() and 0xff) }
            return mapOf("path" to ready.absolutePath, "name" to display,
                         "sha256" to digest, "bytes" to bytes)
        } finally {
            if (pending.exists()) pending.delete()
        }
    }

    private fun sourceEvidence(target: String, version: Long, sources: List<String>): Map<String, Any>? {
        if (!Regex("^[A-Za-z_][A-Za-z0-9_]*(?:\\.[A-Za-z_][A-Za-z0-9_]*)+$").matches(target) ||
            sources.size !in 1..128 || sources.toSet().size != sources.size) return null
        val root = context.cacheDir.canonicalPath + File.separator
        for (path in sources) {
            val file = File(path)
            if (!file.canonicalPath.startsWith(root) || !file.isFile ||
                java.nio.file.Files.isSymbolicLink(file.toPath())) return null
        }
        var expectedSigners: List<String>? = null
        val splitIds = mutableSetOf<String>()
        val hashes = sources.mapIndexed { index, path ->
            val file = File(path)
            val before = digestFile(file)
            val manifest = R09ApkManifest.inspect(file)
            require(manifest.packageName == target && manifest.versionCode == version)
            if (index == 0) require(manifest.split == null)
            else require(manifest.split != null && splitIds.add(manifest.split))
            val signers = R09ApkSignatures.current(file, Build.VERSION.SDK_INT)
            if (index == 0) expectedSigners = signers
            else require(expectedSigners == signers) { "APK member signer mismatch" }
            require(digestFile(file) == before) { "APK changed during verification" }
            before
        }.sorted()
        return mapOf("hashes" to hashes, "signers" to requireNotNull(expectedSigners))
    }

    @Suppress("DEPRECATION")
    private fun verifyInstalled(target: String, version: Long, hashes: List<String>, signers: List<String>): Boolean {
        if (!Regex("^[A-Za-z_][A-Za-z0-9_]*(?:\\.[A-Za-z_][A-Za-z0-9_]*)+$").matches(target) ||
            hashes.size !in 1..128 || signers.isEmpty() ||
            (hashes + signers).any { !Regex("^[0-9a-f]{64}$").matches(it) }) return false
        val observed = installedEvidence(target) ?: return false
        return observed["version"] == version && observed["hashes"] == hashes.sorted() &&
            observed["signers"] == signers.sorted()
    }

    @Suppress("DEPRECATION")
    private fun installedEvidence(target: String): Map<String, Any>? {
        if (!Regex("^[A-Za-z_][A-Za-z0-9_]*(?:\\.[A-Za-z_][A-Za-z0-9_]*)+$").matches(target)) return null
        val flags = if (Build.VERSION.SDK_INT >= 28) PackageManager.GET_SIGNING_CERTIFICATES else PackageManager.GET_SIGNATURES
        val observed = context.packageManager.getPackageInfo(target, flags)
        val version = if (Build.VERSION.SDK_INT >= 28) observed.longVersionCode
                      else observed.versionCode.toLong() and 0xffffffffL
        if (observed.packageName != target) return null
        val signatures = if (Build.VERSION.SDK_INT >= 28) observed.signingInfo?.apkContentsSigners else observed.signatures
        val signers = signatures?.map { shaBytes(it.toByteArray()) }?.distinct()?.sorted()
        if (signers.isNullOrEmpty() || signers.size > 96) return null
        val appInfo = observed.applicationInfo ?: return null
        val installedPaths = listOf(appInfo.sourceDir) + (appInfo.splitSourceDirs?.toList() ?: emptyList())
        if (installedPaths.size !in 1..96 || installedPaths.toSet().size != installedPaths.size) return null
        val hashes = installedPaths.map { path ->
            val apk = File(path)
            require(apk.isFile && apk.length() in 1L..(768L * 1024 * 1024))
            digestFile(apk)
        }.sorted()
        // A concurrent package replacement cannot turn an earlier observation
        // into a receipt for a later installed version.
        val after = context.packageManager.getPackageInfo(target, flags)
        val afterInfo = after.applicationInfo ?: return null
        val afterPaths = listOf(afterInfo.sourceDir) + (afterInfo.splitSourceDirs?.toList() ?: emptyList())
        if (after.lastUpdateTime != observed.lastUpdateTime || afterPaths != installedPaths) return null
        val afterVersion = if (Build.VERSION.SDK_INT >= 28) after.longVersionCode else after.versionCode.toLong() and 0xffffffffL
        val afterSignatures = if (Build.VERSION.SDK_INT >= 28) after.signingInfo?.apkContentsSigners else after.signatures
        val afterSigners = afterSignatures?.map { shaBytes(it.toByteArray()) }?.distinct()?.sorted()
        if (afterVersion != version || afterSigners != signers || after.packageName != target) return null
        return mapOf("package" to target, "version" to version, "hashes" to hashes, "signers" to signers)
    }

    private fun shaBytes(raw: ByteArray): String =
        MessageDigest.getInstance("SHA-256").digest(raw)
            .joinToString("") { "%02x".format(it.toInt() and 0xff) }

    private fun digestFile(path: File): String {
        val md = MessageDigest.getInstance("SHA-256")
        path.inputStream().use { file ->
            val chunk = ByteArray(64 * 1024)
            while (true) {
                val count = file.read(chunk)
                if (count < 0) break
                if (count > 0) md.update(chunk, 0, count)
            }
        }
        return md.digest().joinToString("") { "%02x".format(it.toInt() and 0xff) }
    }

    private fun dispose(path: String): Boolean {
        val item = File(path)
        val parent = runCatching { item.canonicalFile.parentFile }.getOrNull() ?: return false
        if (parent != staging.canonicalFile || !FILE.matches(item.name) ||
            java.nio.file.Files.isSymbolicLink(item.toPath())) return false
        return !item.exists() || (item.isFile && item.delete())
    }
}
