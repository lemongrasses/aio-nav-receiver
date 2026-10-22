import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
}

// Release signing, never from the repository: CI passes the keystore in environment variables (GitHub secrets);
// on a Mac, the Gradle property aionav.signing in ~/.gradle/gradle.properties names a keystore.properties file
// (storeFile, storePassword, keyAlias, keyPassword). Without either, the release APK is left unsigned.
val releaseSigning: Map<String, String>? =
    System.getenv("AIONAV_KEYSTORE")?.takeIf { it.isNotEmpty() }?.let { store ->
        mapOf(
            "storeFile" to store,
            "storePassword" to System.getenv("AIONAV_KEYSTORE_PASSWORD").orEmpty(),
            "keyAlias" to (System.getenv("AIONAV_KEY_ALIAS")?.takeIf { it.isNotEmpty() } ?: "aionav"),
            "keyPassword" to System.getenv("AIONAV_KEY_PASSWORD").orEmpty(),
        )
    } ?: (findProperty("aionav.signing") as String?)?.let { path ->
        val p = Properties().apply { file(path).inputStream().use { load(it) } }
        p.stringPropertyNames().associateWith { p.getProperty(it) }
    }

android {
    namespace = "com.lemongrass.aionav"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.lemongrass.aionav"
        minSdk = 26
        targetSdk = 36
        // Same version as the desktop app; code = major * 10000 + minor * 100 + patch.
        versionCode = 10200
        versionName = "1.2.0"
    }

    androidResources {
        // 繁體中文 + English only; the libraries' other translations are left out.
        localeFilters += listOf("en", "zh-rTW", "b+zh+Hant")
    }

    signingConfigs {
        if (releaseSigning != null) {
            create("release") {
                storeFile = file(releaseSigning.getValue("storeFile"))
                storePassword = releaseSigning.getValue("storePassword")
                keyAlias = releaseSigning.getValue("keyAlias")
                keyPassword = releaseSigning.getValue("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.findByName("release")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        compose = true
    }

    testOptions {
        unitTests.all {
            // The tests read the repository's shared fixtures/ folder (../fixtures from android/), the desktop's
            // i18n.py, the shared glossary and this app's resources straight from the source tree: declare them, so a change re-runs them.
            val repo = rootProject.projectDir.resolve("..")
            it.systemProperty("fixtures.dir", repo.resolve("fixtures").canonicalPath)
            it.inputs.dir(repo.resolve("fixtures")).withPropertyName("sharedFixtures")
            it.inputs.file(repo.resolve("src/aio_receiver/i18n.py")).withPropertyName("desktopI18n")
            it.inputs.file(repo.resolve("docs/TERMINOLOGY.zh-TW.md")).withPropertyName("glossary")
            it.inputs.dir("src/main/res").withPropertyName("appResources")
            it.inputs.dir("src/main/java/com/lemongrass/aionav").withPropertyName("appSources")
        }
    }
}

kotlin {
    jvmToolchain(17)
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.appcompat)            // per-app language (Settings → Language) back to Android 8
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.compose.material.icons)
    debugImplementation(libs.androidx.compose.ui.tooling)

    testImplementation(libs.junit)
    testImplementation(libs.json)
}
