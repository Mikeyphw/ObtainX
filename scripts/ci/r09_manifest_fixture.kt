package dev.imranr.obtainium

import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

/** JVM-only test of the production parser using Android binary XML encoding. */
private fun bytes(n: Int, build: ByteBuffer.() -> Unit) =
    ByteBuffer.allocate(n).order(ByteOrder.LITTLE_ENDIAN).apply(build).array()
private fun ByteBuffer.head(type: Int, header: Int, size: Int) {
    putShort(type.toShort()); putShort(header.toShort()); putInt(size)
}
private fun fixture(utf8: Boolean, split: Boolean = false, duplicate: Boolean = false): ByteArray {
    val strings = listOf("manifest", "package", "dev.example.app", "http://schemas.android.com/apk/res/android",
        "versionCode", "versionCodeMajor", "uses-sdk", "minSdkVersion", "split", "config.arm64_v8a",
        "application", "isSplitRequired", "uses-split", "name", "feature", "configForSplit")
    val payloads = strings.map { s ->
        val encoded = s.toByteArray(if (utf8) Charsets.UTF_8 else Charsets.UTF_16LE)
        if (utf8) byteArrayOf(s.length.toByte(), encoded.size.toByte()) + encoded + byteArrayOf(0)
        else bytes(2) { putShort(s.length.toShort()) } + encoded + byteArrayOf(0, 0)
    }
    val offset = 28 + 4 * strings.size
    val dataSize = payloads.sumOf { it.size }
    val padding = (4 - dataSize % 4) % 4
    val pool = bytes(offset + dataSize + padding) {
        head(1, 28, capacity()); putInt(strings.size); putInt(0); putInt(if (utf8) 256 else 0)
        putInt(offset); putInt(0); var index = 0
        for (s in payloads) { putInt(index); index += s.size }
        for (s in payloads) put(s)
    }
    data class A(val ns: Int, val name: Int, val type: Int, val value: Int)
    fun start(name: Int, attrs: List<A>) = bytes(36 + attrs.size * 20) {
        head(0x102, 16, capacity()); putInt(1); putInt(-1); putInt(-1); putInt(name)
        putShort(20); putShort(20); putShort(attrs.size.toShort()); putShort(0); putShort(0); putShort(0)
        for (a in attrs) {
            putInt(a.ns); putInt(a.name); putInt(if (a.type == 3) a.value else -1)
            putShort(8); put(0); put(a.type.toByte()); putInt(a.value)
        }
    }
    fun end(name: Int) = bytes(24) { head(0x103, 16, 24); putInt(1); putInt(-1); putInt(-1); putInt(name) }
    val root = mutableListOf(A(-1,1,3,2), A(3,4,0x10,2), A(3,5,0x10,1))
    if (split) root.add(A(-1,8,3,9))
    if (duplicate) root.add(root.first())
    val body = pool + start(0, root) + start(6, listOf(A(3,7,0x10,26))) + end(6) +
        start(10, listOf(A(3,11,0x12,if (split) 0 else 1))) + end(10) +
        start(12, listOf(A(3,13,3,14))) + end(12) + end(0)
    return bytes(8) { head(3,8,8+body.size) } + body
}
fun main() {
    var checks = 0
    for (utf8 in listOf(true,false)) {
        val base = R09ApkManifest.parse(fixture(utf8))
        check(base.packageName == "dev.example.app" && base.versionCode == 4294967298L && base.minSdk == 26)
        check(base.split == null && base.splitRequired && base.requiredSplits == listOf("feature")); checks += 2
        val split = R09ApkManifest.parse(fixture(utf8, split = true))
        check(split.split == "config.arm64_v8a" && !split.splitRequired); checks++
        check(runCatching { R09ApkManifest.parse(fixture(utf8, duplicate = true)) }.isFailure); checks++
        check(runCatching { R09ApkManifest.parse(fixture(utf8).dropLast(1).toByteArray()) }.isFailure); checks++
    }
    val file = File.createTempFile("r09-test", ".apk")
    try {
        ZipOutputStream(file.outputStream()).use { zip ->
            zip.putNextEntry(ZipEntry("AndroidManifest.xml")); zip.write(fixture(true)); zip.closeEntry()
            zip.putNextEntry(ZipEntry("lib/arm64-v8a/libtest.so")); zip.write(byteArrayOf(1)); zip.closeEntry()
        }
        check(R09ApkManifest.inspect(file).nativeAbis == listOf("arm64-v8a")); checks++
        ZipOutputStream(file.outputStream()).use { zip ->
            zip.putNextEntry(ZipEntry("not-a-manifest")); zip.write(byteArrayOf(1)); zip.closeEntry()
        }
        check(runCatching { R09ApkManifest.inspect(file) }.isFailure); checks++
    } finally { file.delete() }
    println("R09 JVM binary-manifest fixture: $checks checks passed")
}
