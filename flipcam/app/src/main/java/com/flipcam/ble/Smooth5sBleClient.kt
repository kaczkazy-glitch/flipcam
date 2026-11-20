package com.flipcam.ble

import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Context
import android.os.Build
import java.util.UUID
import java.util.concurrent.atomic.AtomicInteger

/**
 * Optional gimbal link. Every method degrades to a no-op when no gimbal is present, so the
 * camera and skeleton tracker never depend on it.
 *
 * Callers must hold BLUETOOTH_SCAN and BLUETOOTH_CONNECT at runtime.
 */
@SuppressLint("MissingPermission")
class Smooth5sBleClient(
    context: Context,
    private val listener: Listener,
) {

    interface Listener {
        fun onGimbalState(connected: Boolean, name: String?)
        fun onGimbalStatus(bytes: ByteArray)
    }

    private val appContext = context.applicationContext
    private val adapter: BluetoothAdapter? =
        (appContext.getSystemService(Context.BLUETOOTH_SERVICE) as? BluetoothManager)?.adapter

    private val serviceUuid: UUID = UUID.fromString(GimbalFrame.SERVICE_UUID)
    private val txUuid: UUID = UUID.fromString(GimbalFrame.TX_UUID)
    private val rxUuid: UUID = UUID.fromString(GimbalFrame.RX_UUID)

    private var gatt: BluetoothGatt? = null
    private var txChar: BluetoothGattCharacteristic? = null
    private val sequence = AtomicInteger(1)
    private var scanning = false

    @Volatile
    var isConnected: Boolean = false
        private set

    val isSupported: Boolean get() = adapter != null && adapter.isEnabled

    private val scanCallback = object : ScanCallback() {
        override fun onScanResult(callbackType: Int, result: ScanResult) {
            val device = result.device ?: return
            if (!looksLikeGimbal(result)) return
            stopScan()
            connect(device)
        }
    }

    private fun looksLikeGimbal(result: ScanResult): Boolean {
        val name = result.scanRecord?.deviceName ?: result.device?.name
        if (name?.uppercase()?.contains(GimbalFrame.NAME_PREFIX) == true) return true
        val manufacturer = result.scanRecord?.manufacturerSpecificData ?: return false
        return manufacturer.get(GimbalFrame.MANUFACTURER_ID) != null
    }

    @SuppressLint("MissingPermission")
    fun startScan() {
        val scanner = adapter?.bluetoothLeScanner ?: return
        if (scanning || isConnected) return
        scanning = true
        val settings = ScanSettings.Builder()
            .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY)
            .build()
        runCatching { scanner.startScan(emptyList(), settings, scanCallback) }
    }

    @SuppressLint("MissingPermission")
    fun stopScan() {
        if (!scanning) return
        scanning = false
        runCatching { adapter?.bluetoothLeScanner?.stopScan(scanCallback) }
    }

    private fun connect(device: BluetoothDevice) {
        gatt?.close()
        gatt = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            device.connectGatt(appContext, true, gattCallback, BluetoothDevice.TRANSPORT_LE)
        } else {
            device.connectGatt(appContext, true, gattCallback)
        }
    }

    private val gattCallback = object : BluetoothGattCallback() {

        override fun onConnectionStateChange(gatt: BluetoothGatt, status: Int, newState: Int) {
            if (newState == BluetoothProfile.STATE_CONNECTED) {
                gatt.discoverServices()
            } else {
                isConnected = false
                txChar = null
                listener.onGimbalState(false, null)
            }
        }

        override fun onServicesDiscovered(gatt: BluetoothGatt, status: Int) {
            val service = gatt.getService(serviceUuid) ?: return
            txChar = service.getCharacteristic(txUuid)
            val rx = service.getCharacteristic(rxUuid)
            if (rx != null) {
                gatt.setCharacteristicNotification(rx, true)
                rx.getDescriptor(UUID.fromString(CCCD_UUID))?.let { descriptor ->
                    descriptor.value = CCCD_ENABLE
                    gatt.writeDescriptor(descriptor)
                }
            }
            isConnected = txChar != null
            listener.onGimbalState(isConnected, gatt.device?.name)
            if (isConnected) centerAll()
        }

        override fun onCharacteristicChanged(
            gatt: BluetoothGatt,
            characteristic: BluetoothGattCharacteristic,
            value: ByteArray,
        ) {
            listener.onGimbalStatus(value)
        }
    }

    /**
     * Sends one gentle step. [pan] and [tilt] use the 0..4095 range centred on 2048, the same
     * scale as the verified wire format. Call [hold] when tracking releases the subject.
     */
    fun sendPanTilt(pan: Int, tilt: Int, speed: Int) {
        val link = gatt ?: return
        val characteristic = txChar ?: return
        if (!isConnected) return

        if (pan != GimbalFrame.CENTER || tilt != GimbalFrame.CENTER) {
            write(link, characteristic, GimbalFrame.motionFrame(
                GimbalFrame.AXIS_PAN, pan, speed, sequence.getAndIncrement()
            ))
            write(link, characteristic, GimbalFrame.motionFrame(
                GimbalFrame.AXIS_TILT, tilt, speed, sequence.getAndIncrement()
            ))
        } else {
            hold()
        }
    }

    /** Holds both driven axes, which stops motion on this firmware. */
    fun hold() {
        val link = gatt ?: return
        val characteristic = txChar ?: return
        if (!isConnected) return
        write(link, characteristic, GimbalFrame.holdFrame(
            GimbalFrame.AXIS_PAN, sequence.getAndIncrement()
        ))
        write(link, characteristic, GimbalFrame.holdFrame(
            GimbalFrame.AXIS_TILT, sequence.getAndIncrement()
        ))
    }

    /** Holds pan, tilt and roll so the camera rests level when the link comes up. */
    private fun centerAll() {
        val link = gatt ?: return
        val characteristic = txChar ?: return
        hold()
        write(
            link,
            characteristic,
            GimbalFrame.holdFrame(GimbalFrame.AXIS_ROLL, sequence.getAndIncrement()),
        )
    }

    private fun write(
        gatt: BluetoothGatt,
        characteristic: BluetoothGattCharacteristic,
        frame: ByteArray,
    ) {
        runCatching {
            gatt.writeCharacteristic(
                characteristic,
                frame,
                BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE,
            )
        }
    }

    fun close() {
        stopScan()
        runCatching { gatt?.disconnect() }
        runCatching { gatt?.close() }
        gatt = null
        txChar = null
        isConnected = false
    }

    private companion object {
        const val CCCD_UUID = "00002902-0000-1000-8000-00805f9b34fb"
        val CCCD_ENABLE: ByteArray = byteArrayOf(0x01, 0x00)
    }
}
