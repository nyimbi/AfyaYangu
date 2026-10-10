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
	// android.jar's org.json is a stub that throws on every call in JVM unit tests, so the
	// catalogue parse cannot be exercised without a real implementation on the test classpath.
	// `returnDefaultValues` would silence it by returning defaults — which tests nothing.
	testImplementation("org.json:json:20250107")
}