plugins { id("com.android.application") }

android {
    namespace = "com.edgepilot.mobile"
    compileSdk = 35
    defaultConfig {
        applicationId = "com.edgepilot.mobile"
        minSdk = 26
        targetSdk = 35
        versionCode = 1912
        versionName = "0.19.12"
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}
