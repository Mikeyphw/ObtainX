import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    id("com.android.library")
}

android {
    namespace = "dev.imranr.obtainium.evidence"
    compileSdk = 37
    defaultConfig { minSdk = 26 }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_21
        targetCompatibility = JavaVersion.VERSION_21
        isCoreLibraryDesugaringEnabled = true
    }
}
kotlin {
    compilerOptions { jvmTarget.set(JvmTarget.JVM_21) }
}
dependencies {
    // Exact AGP-aligned Android APK Signature Scheme verifier, including split APKs.
    implementation("com.android.tools.build:apksig:9.3.1")
    coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.5")
}
