// Confirmed UI control range. The API v2 offset is retained only for compatibility;
// it is not evidence that negative physical preamp gain has been discovered.
const GainScale = Object.freeze({
  min: 0,
  max: 50,
  fromApi(value) {
    if (!Number.isFinite(value)) throw new TypeError('Ganancia recibida inválida');
    return Math.max(0, Math.min(50, Math.round(value + 8)));
  },
  toApi(value) {
    if (!Number.isInteger(value) || value < 0 || value > 50) {
      throw new RangeError('El control de ganancia debe estar entre 0 y 50');
    }
    return value - 8;
  },
});
