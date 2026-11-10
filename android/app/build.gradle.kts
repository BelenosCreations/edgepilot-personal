plugins { id("com.android.application") }

// Only an explicitly owner-controlled HTTPS staging hostname may be embedded
// in the separate staging package. Missing input deliberately builds an
// unusable .invalid host; it can never silently connect to production.
val stagingHost = providers.gradleProperty("edgePilotStagingHost")
    .orElse("unconfigured.edgepilot.invalid").get()
val hostnameSyntax = Regex("""^(?:[a-z0-9]+(?:-[a-z0-9]+)*\.)+[a-z0-9]+$""")
require(hostnameSyntax.matches(stagingHost) &&
    (stagingHost == "unconfigured.edgepilot.invalid" ||
    (stagingHost.endsWith(".belenoscreations.biz") &&
     stagingHost != "edgepilot.belenoscreations.biz"))) {
    "Staging hostname must be a distinct approved belenoscreations.biz subdomain"
}

android {
    namespace = "com.edgepilot.mobile"
    compileSdk = 35
    buildFeatures { buildConfig = true }
    defaultConfig {
        applicationId = "com.edgepilot.mobile"
        minSdk = 26
        targetSdk = 35
        versionCode = 1917
        versionName = "0.19.17"
        buildConfigField("String", "EDGE_HOST", "\"edgepilot.belenoscreations.biz\"")
        manifestPlaceholders["edgePilotAppLabel"] = "EdgePilot"
    }
    buildTypes {
        // A different package ID allows safe side-by-side test installation.
        // No backend flag, real broker key, password or domain secret is bundled.
        create("staging") {
            initWith(getByName("release"))
            applicationIdSuffix = ".staging"
            versionNameSuffix = "-staging"
            isDebuggable = false
            buildConfigField("String", "EDGE_HOST", "\"$stagingHost\"")
            manifestPlaceholders["edgePilotAppLabel"] = "EdgePilot Staging"
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

// WebView forwards real WebAuthn to Android Credential Manager on supported
// versions only. Device biometrics and passkeys stay inside providers.
dependencies {
    implementation("androidx.webkit:webkit:1.16.0")
    implementation("androidx.credentials:credentials:1.6.0")
    implementation("androidx.credentials:credentials-play-services-auth:1.6.0")
}
