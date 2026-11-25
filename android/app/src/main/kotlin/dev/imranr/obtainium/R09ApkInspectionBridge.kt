package dev.imranr.obtainium

import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import io.flutter.plugin.common.BinaryMessenger
import io.flutter.plugin.common.MethodChannel
import io.flutter.plugin.common.StandardMethodCodec
import java.io.File
import java.security.MessageDigest

/** Read-only and confined to private, disposable R09 review files. */
internal class R09ApkInspectionBridge(context: Context, messenger: BinaryMessenger) {
    private val app = context.applicationContext
    private val channel = MethodChannel(messenger, "dev.imranr.obtainium/r09_apk_inspection",
        StandardMethodCodec.INSTANCE, messenger.makeBackgroundTaskQueue())
    init {
        channel.setMethodCallHandler { call, result ->
            if (call.method != "inspect") {
                result.notImplemented()
            } else {
                try {
                    val path = requireNotNull(call.argument<String>("path"))
                    result.success(inspect(path))
                } catch (_: Exception) {
                    // Never expose file paths, arbitrary manifest text or platform diagnostics.
                    result.error("R09_APK_INSPECTION_REFUSED", "APK inspection refused", null)
                }
            }
        }
    }
    @Suppress("DEPRECATION")
    private fun inspect(path: String): Map<String, Any?> {
        val root = app.cacheDir.canonicalFile
        val original = File(path).absoluteFile
        val file = original.canonicalFile
        require(file.isFile && file.length() in 1L..(768L * 1024 * 1024))
        val lexicalRoot = app.cacheDir.absoluteFile
        require(original.path.startsWith(lexicalRoot.path + File.separator))
        var component = lexicalRoot
        for (part in original.relativeTo(lexicalRoot).invariantSeparatorsPath.split('/')) {
            require(part.isNotEmpty() && part != "." && part != "..")
            component = File(component, part)
            require(!java.nio.file.Files.isSymbolicLink(component.toPath()))
        }
        require(component.canonicalFile == file)
        require(file.path.startsWith(root.path + File.separator))
        val parts = file.relativeTo(root).invariantSeparatorsPath.split('/')
        require(parts.size >= 2 && parts.first().matches(Regex("r09-review-[A-Za-z0-9_-]+")))
        val manifest = R09ApkManifest.inspect(file)
        val pm = app.packageManager
        val flags = if (Build.VERSION.SDK_INT >= 28) PackageManager.GET_SIGNING_CERTIFICATES else PackageManager.GET_SIGNATURES
        val info = if (manifest.split == null) pm.getPackageArchiveInfo(file.path, flags)
            else runCatching { pm.getPackageArchiveInfo(file.path, flags) }.getOrNull()
        if (manifest.split == null) require(info != null) { "Base metadata unavailable" }
        if (info != null) {
            val version = if (Build.VERSION.SDK_INT >= 28) info.longVersionCode else info.versionCode.toLong() and 0xffffffffL
            require(info.packageName == manifest.packageName && version == manifest.versionCode)
            if (manifest.split == null) {
                require(info.applicationInfo?.minSdkVersion == manifest.minSdk)
            }
        }
        val signatures = if (Build.VERSION.SDK_INT >= 28) info?.signingInfo?.apkContentsSigners else info?.signatures
        val signers = signatures?.map { signature ->
            MessageDigest.getInstance("SHA-256").digest(signature.toByteArray())
                .joinToString("") { byte -> "%02x".format(byte.toInt() and 255) }
        }?.distinct()?.sorted().orEmpty()
        return mapOf(
            "packageName" to manifest.packageName, "versionCode" to manifest.versionCode,
            "versionName" to info?.versionName, "split" to manifest.split,
            "configForSplit" to manifest.configForSplit, "minSdk" to manifest.minSdk,
            "splitRequired" to manifest.splitRequired, "requiredSplits" to manifest.requiredSplits,
            "requiredSplitTypes" to manifest.requiredSplitTypes, "splitTypes" to manifest.splitTypes,
            "nativeAbis" to manifest.nativeAbis, "signers" to signers,
        )
    }
}
