package dev.imranr.obtainium

import io.flutter.embedding.engine.plugins.FlutterPlugin

/** Registered by Flutter on every engine, including WorkManager and foreground-task engines. */
class ObtainxNativeEvidencePlugin : FlutterPlugin {
    private var local: R02LocalArchiveBridge? = null
    private var inspection: R09ApkInspectionBridge? = null
    override fun onAttachedToEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        check(local == null && inspection == null)
        local = R02LocalArchiveBridge(binding.applicationContext, binding.binaryMessenger)
        inspection = R09ApkInspectionBridge(binding.applicationContext, binding.binaryMessenger)
    }
    override fun onDetachedFromEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        local?.close()
        inspection?.close()
        local = null
        inspection = null
    }
}
