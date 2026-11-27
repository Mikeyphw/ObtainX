package dev.imranr.obtainium

import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.charset.CodingErrorAction
import java.util.zip.ZipFile

/** Bounded binary XML inspection. Certificate evidence is collected separately. */
internal data class R09Manifest(val packageName: String, val versionCode: Long,
    val split: String?, val configForSplit: String?, val minSdk: Int?,
    val splitRequired: Boolean, val requiredSplits: List<String>,
    val requiredSplitTypes: List<String>, val splitTypes: List<String>, val nativeAbis: List<String>)

internal object R09ApkManifest {
    const val LIMIT = 4 * 1024 * 1024
    private const val ANDROID = "http://schemas.android.com/apk/res/android"
    private val pkg = Regex("[A-Za-z_][A-Za-z0-9_]*(\\.[A-Za-z_][A-Za-z0-9_]*)+")
    private val role = Regex("[A-Za-z0-9_.-]{1,255}")
    fun inspect(file: File): R09Manifest = ZipFile(file).use { zip ->
        var manifest: ByteArray? = null
        val abis = sortedSetOf<String>()
        var count = 0
        val entries = zip.entries()
        while (entries.hasMoreElements()) {
            val entry = entries.nextElement()
            require(++count <= 100_000) { "APK entry limit" }
            if (entry.name == "AndroidManifest.xml") {
                require(manifest == null && !entry.isDirectory && entry.size in 8L..LIMIT.toLong())
                manifest = zip.getInputStream(entry).use { stream ->
                    val out = java.io.ByteArrayOutputStream()
                    val buffer = ByteArray(8192)
                    while (true) {
                        val n = stream.read(buffer)
                        if (n < 0) break
                        require(out.size() + n <= LIMIT)
                        out.write(buffer, 0, n)
                    }
                    out.toByteArray().also { require(it.size.toLong() == entry.size) }
                }
            }
            if (!entry.isDirectory && entry.name.startsWith("lib/") && entry.name.endsWith(".so")) {
                val parts = entry.name.split('/')
                require(parts.size == 3 && parts[1].matches(Regex("[A-Za-z0-9_-]{1,32}")))
                abis.add(parts[1]); require(abis.size <= 32)
            }
        }
        parse(requireNotNull(manifest), abis.toList())
    }
    private data class Value(val raw: String?, val type: Int, val data: Int, val pool: List<String>) {
        fun text(): String {
            require(type == 3)
            val value = requireNotNull(pool.getOrNull(data))
            require(raw == null || raw == value)
            return value
        }
        fun number(): Int? = if (type == 0x10 || type == 0x11) data else text().toIntOrNull()
        fun bool(): Boolean = if (type == 0x12) data != 0 else when (text()) {
            "true" -> true
            "false" -> false
            else -> error("Unsupported boolean attribute")
        }
    }
    fun parse(bytes: ByteArray, abis: List<String> = emptyList()): R09Manifest {
        require(bytes.size in 8..LIMIT)
        val b = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
        fun u16(p: Int) = b.getShort(p).toInt() and 0xffff
        fun i32(p: Int) = b.getInt(p)
        require(u16(0) == 3 && u16(2) == 8 && i32(4) == bytes.size)
        var pool: List<String>? = null
        var packageName: String? = null
        var versionCode: Long? = null
        var split: String? = null
        var config: String? = null
        var minSdk: Int? = null
        var required = false
        val requiredSplits = mutableListOf<String>()
        var requiredTypes = emptyList<String>()
        var splitTypes = emptyList<String>()
        val stack = mutableListOf<String>()
        var seenRoot = false
        var seenSdk = false
        var p = 8
        fun types(value: String?) = value.orEmpty().split(',').map { it.trim() }
            .filter { it.isNotEmpty() }.also { require(it.size <= 64 && it.all(role::matches)) }
        while (p < bytes.size) {
            require(bytes.size - p >= 8)
            val type = u16(p); val header = u16(p + 2); val size = i32(p + 4)
            require(header >= 8 && size >= header && size <= bytes.size - p)
            val end = p + size
            if (type == 1) {
                require(pool == null && header >= 28)
                val count = i32(p + 8); val styles = i32(p + 12); val start = i32(p + 20); val styleStart = i32(p + 24)
                val utf8 = i32(p + 16) and 0x100 != 0
                require(count in 1..50_000 && styles in 0..50_000 && start >= header + (count + styles) * 4 && start < size && (styleStart == 0 || styleStart in start..size))
                val stringsEnd = if (styleStart == 0) end else p + styleStart
                fun readString(offset: Int): String {
                    require(offset >= 0 && offset < stringsEnd - (p + start))
                    var q = p + start + offset
                    fun len8(): Int {
                        require(q < stringsEnd); val n = bytes[q++].toInt() and 255
                        if (n and 128 == 0) return n
                        require(q < stringsEnd); return ((n and 127) shl 8) or (bytes[q++].toInt() and 255)
                    }
                    fun len16(): Int {
                        require(q + 2 <= stringsEnd); val n = u16(q); q += 2
                        if (n and 0x8000 == 0) return n
                        require(q + 2 <= stringsEnd); val tail = u16(q); q += 2
                        return ((n and 0x7fff) shl 16) or tail
                    }
                    val length: Int
                    val charset = if (utf8) { len8(); length = len8(); Charsets.UTF_8 }
                        else { val units = len16(); require(units <= LIMIT / 2); length = units * 2; Charsets.UTF_16LE }
                    val terminator = if (utf8) 1 else 2
                    require(length >= 0 && length <= stringsEnd - q - terminator)
                    require((0 until terminator).all { bytes[q + length + it] == 0.toByte() })
                    return charset.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
                        .onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(bytes, q, length)).toString()
                }
                var chars = 0L
                val cache = mutableMapOf<Int, String>()
                pool = List(count) { index -> cache.getOrPut(i32(p + header + index * 4)) {
                    readString(i32(p + header + index * 4))
                }.also { chars += it.length; require(chars <= LIMIT * 2L) } }
            } else if (type == 0x102 || type == 0x103) {
                val strings = requireNotNull(pool)
                fun string(index: Int) = strings.getOrNull(index) ?: error("Invalid XML string index")
                require(header >= 16 && size >= header + (if (type == 0x102) 20 else 8))
                val ext = p + header; val name = string(i32(ext + 4))
                if (type == 0x103) {
                    require(stack.isNotEmpty() && stack.removeAt(stack.lastIndex) == name)
                } else {
                    val offset = u16(ext + 8); val stride = u16(ext + 10); val count = u16(ext + 12)
                    require(offset >= 20 && stride >= 20 && count <= 1024 && offset + count.toLong() * stride <= size - header)
                    val attrs = mutableMapOf<Pair<String?, String>, Value>()
                    for (index in 0 until count) {
                        val at = ext + offset + index * stride
                        val ns = i32(at).let { if (it == -1) null else string(it) }
                        val key = string(i32(at + 4)); val raw = i32(at + 8).let { if (it == -1) null else string(it) }
                        require(u16(at + 12) == 8)
                        require(attrs.put(ns to key, Value(raw, bytes[at + 15].toInt() and 255, i32(at + 16), strings)) == null)
                    }
                    fun attr(key: String, ns: String? = ANDROID) = attrs[ns to key]
                    if (stack.isEmpty()) {
                        require(!seenRoot && name == "manifest"); seenRoot = true
                        packageName = attr("package", null)?.text()
                        val low = requireNotNull(attr("versionCode")?.number()).toLong() and 0xffffffffL
                        val high = (attr("versionCodeMajor")?.number() ?: 0).toLong(); require(high >= 0)
                        versionCode = (high shl 32) or low
                        split = attr("split", null)?.text()?.takeIf { it.isNotEmpty() }
                        val plainConfig = attr("configForSplit", null)?.text()
                        val androidConfig = attr("configForSplit")?.text()
                        require(plainConfig == null || androidConfig == null || plainConfig == androidConfig)
                        config = (plainConfig ?: androidConfig)?.takeIf { it.isNotEmpty() }
                        requiredTypes = types(attr("requiredSplitTypes")?.text())
                        splitTypes = types(attr("splitTypes")?.text())
                        required = attr("isSplitRequired")?.bool() == true || requiredTypes.isNotEmpty()
                    } else if (stack.size == 1) {
                        if (name == "uses-sdk") {
                            require(!seenSdk); seenSdk = true
                            val sdk = attr("minSdkVersion"); minSdk = if (sdk == null) 1 else requireNotNull(sdk.number())
                            require(minSdk > 0)
                        } else if (name == "uses-split") {
                            requiredSplits.add(requireNotNull(attr("name")?.text())); require(requiredSplits.size <= 64 && requiredSplits.all(role::matches))
                        } else if (name == "application") required = required || attr("isSplitRequired")?.bool() == true
                    }
                    stack.add(name); require(stack.size <= 64)
                }
            }
            p = end
        }
        val name = requireNotNull(packageName)
        require(stack.isEmpty() && seenRoot && name.length <= 255 && pkg.matches(name))
        require(split == null || role.matches(split)); require(config == null || role.matches(config))
        return R09Manifest(name, requireNotNull(versionCode), split, config, minSdk ?: if (split == null) 1 else null,
            required, requiredSplits.distinct(), requiredTypes, splitTypes, abis)
    }
}
