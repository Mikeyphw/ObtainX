package dev.imranr.obtainium

import com.android.apksig.ApkVerifier
import java.io.File
import java.security.MessageDigest

/** Verify actual APK signatures, including standalone configuration APKs.
 * Verify the signing scheme used on the current Android API, not historical
 * certificates or a certificate merely listed in an unverified signing block.
 */
internal object R09ApkSignatures {
    fun current(file: File, sdk: Int): List<String> {
        require(sdk >= 26 && file.isFile && file.length() in 1L..(768L * 1024 * 1024))
        val result = ApkVerifier.Builder(file)
            .setMinCheckedPlatformVersion(sdk)
            .setMaxCheckedPlatformVersion(sdk)
            .build().verify()
        require(result.isVerified) { "APK signature verification refused" }
        val certs = result.signerCertificates.map { cert ->
            MessageDigest.getInstance("SHA-256").digest(cert.encoded)
                .joinToString("") { byte -> "%02x".format(byte.toInt() and 255) }
        }
        require(certs.isNotEmpty() && certs.size <= 64 && certs.toSet().size == certs.size)
        return certs.sorted()
    }
}
