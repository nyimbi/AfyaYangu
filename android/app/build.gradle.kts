plugins {
	id("com.android.application")
}

android {
	namespace = "ke.go.health.afyayangu"
	compileSdk = 35

	defaultConfig {
		applicationId = "ke.go.health.afyayangu"
		minSdk = 24
		targetSdk = 35
		versionCode = 1
		versionName = "2.0.0"
	}

	buildTypes {
		release {
			isMinifyEnabled = false
		}
	}
}

dependencies {
	testImplementation("junit:junit:4.13.2")
}