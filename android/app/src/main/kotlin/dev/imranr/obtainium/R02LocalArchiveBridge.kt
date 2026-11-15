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
        private val TOKEN = Regex("^[A-Za-z0-9_-]{8,80}$")
        private val FILE = Regex("^r02-[0-9a-f-]{36}\\.(?:apk|apks|apkm|xapk|zip|tar|tgz|tar\\.gz|tar\\.bz2|tar\\.xz)$")
        private val SUFFIXES = listOf(".tar.gz", ".tar.bz2", ".tar.xz", ".apks", ".apkm", ".xapk", ".apk", ".zip", ".tar", ".tgz")
    }

    init {
        channel.setMethodCallHandler { call, reply ->
            when (call.method) {
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
        try {
            val input = context.contentResolver.openInputStream(uri)
                ?: throw IllegalArgumentException("Document content could not be opened")
            input.use { source ->
                FileOutputStream(pending, false).use { target ->
                    val buffer = ByteArray(64 * 1024)
                    while (true) {
                        if (cancel.get()) throw IllegalStateException("User cancelled import")
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

    @Suppress("DEPRECATION")
    private fun sourceEvidence(target: String, version: Long, sources: List<String>): Map<String, Any>? {
        if (!Regex("^[A-Za-z_][A-Za-z0-9_]*(?:\\.[A-Za-z_][A-Za-z0-9_]*)+$").matches(target) ||
            sources.size !in 1..128 || sources.toSet().size != sources.size) return null
        val root = context.cacheDir.canonicalPath + File.separator
        for (path in sources) {
            val file = File(path)
            if (!file.canonicalPath.startsWith(root) || !file.isFile ||
                java.nio.file.Files.isSymbolicLink(file.toPath())) return null
        }
        val flags = PackageManager.GET_SIGNING_CERTIFICATES
        val archive = context.packageManager.getPackageArchiveInfo(sources.first(), flags) ?: return null
        val observedVersion = if (Build.VERSION.SDK_INT >= 28) archive.longVersionCode
                              else archive.versionCode.toLong()
        if (archive.packageName != target || observedVersion != version) return null
        val signers = archive.signingInfo?.apkContentsSigners?.map { shaBytes(it.toByteArray()) }?.sorted()
        if (signers.isNullOrEmpty()) return null
        return mapOf("hashes" to sources.map { digestFile(File(it)) }.sorted(),
                     "signers" to signers)
    }

    @Suppress("DEPRECATION")
    private fun verifyInstalled(target: String, version: Long, hashes: List<String>, signers: List<String>): Boolean {
        if (!Regex("^[A-Za-z_][A-Za-z0-9_]*(?:\\.[A-Za-z_][A-Za-z0-9_]*)+$").matches(target) ||
            hashes.size !in 1..128 || signers.isEmpty() ||
            (hashes + signers).any { !Regex("^[0-9a-f]{64}$").matches(it) }) return false
        val observed = context.packageManager.getPackageInfo(target, PackageManager.GET_SIGNING_CERTIFICATES)
        val observedVersion = if (Build.VERSION.SDK_INT >= 28) observed.longVersionCode
                              else observed.versionCode.toLong()
        if (observed.packageName != target || observedVersion != version) return false
        val installedSigners = observed.signingInfo?.apkContentsSigners?.map { shaBytes(it.toByteArray()) }?.sorted()
        if (signers.sorted() != installedSigners) return false
        val appInfo = observed.applicationInfo ?: return false
        val installedPaths = listOf(appInfo.sourceDir) + (appInfo.splitSourceDirs?.toList() ?: emptyList())
        if (installedPaths.size != hashes.size) return false
        return installedPaths.map { digestFile(File(it)) }.sorted() == hashes.sorted()
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
