package ke.go.health.afyayangu

import org.junit.Assert.assertEquals
import org.junit.Test

class SenseBandsTest {
	@Test fun respirationBands() {
		assertEquals("normal", SenseBands.respiration(16.0))
		assertEquals("alert", SenseBands.respiration(9.0))
		assertEquals("alert", SenseBands.respiration(26.0))
	}

	@Test fun coughBands() {
		assertEquals("normal", SenseBands.cough(5.0))
		assertEquals("watch", SenseBands.cough(18.0))
		assertEquals("alert", SenseBands.cough(31.0))
	}

	@Test fun ppgBands() {
		assertEquals("normal", SenseBands.ppg(72.0))
		assertEquals("watch", SenseBands.ppg(50.0))
		assertEquals("alert", SenseBands.ppg(140.0))
	}
}