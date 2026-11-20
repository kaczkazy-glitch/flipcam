package com.flipcam.ble

/**
 * Zhiyun Smooth 5S framing, verified against a live unit (see ZHIYUN_PROTOCOL.md).
 *
 * Envelope: `24 3C | len(2, LE) | 18 12 | seq | 01 | cmd | payload | crc(2, LE)`
 * where `len` counts bytes from the format id through the payload, and the CRC is
 * CRC-16/XMODEM over exactly those bytes.
 */
object GimbalFrame {

    const val SERVICE_UUID = "0000fee9-0000-1000-8000-00805f9b34fb"
    const val TX_UUID = "d44bc439-abfd-45a2-b575-925416129600" // write-without-response
    const val RX_UUID = "d44bc439-abfd-45a2-b575-925416129601" // notify
    const val NAME_PREFIX = "SMOOTH"
    const val MANUFACTURER_ID = 0x0509

    const val AXIS_PAN = 0x01
    const val AXIS_TILT = 0x02
    const val AXIS_ROLL = 0x03

    /** 2048 holds the axis; values on either side drive opposite directions. */
    const val CENTER = 2048
    const val MAX_VALUE = 4095

    private const val MAGIC_1 = 0x24
    private const val MAGIC_2 = 0x3C
    private const val FORMAT_ID_1 = 0x18
    private const val FORMAT_ID_2 = 0x12
    private const val DIRECTION_HOST = 0x01
    private const val MOTION_BODY_LEN = 8

    fun motionFrame(axis: Int, value: Int, speed: Int, sequence: Int): ByteArray {
        val v = value.coerceIn(0, MAX_VALUE)
        val s = speed.coerceIn(1, 255)
        val body = byteArrayOf(
            FORMAT_ID_1.toByte(),
            FORMAT_ID_2.toByte(),
            (sequence and 0xFF).toByte(),
            DIRECTION_HOST.toByte(),
            axis.toByte(),
            (v and 0xFF).toByte(),
            ((v shr 8) and 0xFF).toByte(),
            s.toByte(),
        )
        val crc = crc16Xmodem(body)
        return ByteArray(4 + body.size + 2).also { frame ->
            frame[0] = MAGIC_1.toByte()
            frame[1] = MAGIC_2.toByte()
            frame[2] = (MOTION_BODY_LEN and 0xFF).toByte()
            frame[3] = 0
            body.copyInto(frame, 4)
            frame[12] = (crc and 0xFF).toByte()
            frame[13] = ((crc shr 8) and 0xFF).toByte()
        }
    }

    /** Hold frame: the closest thing this firmware has to "stop". */
    fun holdFrame(axis: Int, sequence: Int): ByteArray =
        motionFrame(axis, CENTER, 1, sequence)

    fun crc16Xmodem(data: ByteArray): Int {
        var crc = 0x0000
        for (byte in data) {
            crc = crc xor ((byte.toInt() and 0xFF) shl 8)
            repeat(8) {
                crc = if (crc and 0x8000 != 0) {
                    ((crc shl 1) xor 0x1021) and 0xFFFF
                } else {
                    (crc shl 1) and 0xFFFF
                }
            }
        }
        return crc
    }
}
