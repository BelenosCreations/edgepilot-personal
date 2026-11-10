plugins { id("com.android.application") }

android {
    namespace = "com.edgepilot.mobile"
    compileSdk = 35
    defaultConfig {
        applicationId = "com.edgepilot.mobile"
        minSdk = 26
        targetSdk = 35
        versionCode = 1917
        versionName = "0.19.17"
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

// WebView forwards real WebAuthn to Android Credential Manager on supported
// versions only. Device biometrics and passkeys stay inside credential providers.
dependencies {
    implementation("androidx.webkit:webkit:1.16.0")
    implementation("androidx.credentials:credentials:1.6.0")
    implementation("androidx.credentials:credentials-play-services-auth:1.6.0")
}
