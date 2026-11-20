package com.flipcam.gl

import android.content.Context
import android.graphics.SurfaceTexture
import android.opengl.GLES11Ext
import android.opengl.GLES30
import android.opengl.GLSurfaceView
import android.view.Surface
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.FloatBuffer
import javax.microedition.khronos.egl.EGLConfig
import javax.microedition.khronos.opengles.GL10

/**
 * Live viewfinder surface. An external OES texture receives the Camera2 preview and a GLSL pass
 * applies a 3D `.cube` LUT. The recorded stream is never touched, so video stays Log/HLG.
 */
class LutSurfaceView(context: Context) : GLSurfaceView(context) {

    private val renderer = PreviewRenderer()

    /** Fires once the GL context exists and a preview Surface is available. */
    var onPreviewSurface: ((Surface) -> Unit)? = null

    var lutEnabled: Boolean = true
        set(value) {
            field = value
            requestRender()
        }

    var lutStrength: Float = 1f
        set(value) {
            field = value.coerceIn(0f, 1f)
            requestRender()
        }

    init {
        setEGLContextClientVersion(3)
        preserveEGLContextOnPause = true
        setRenderer(renderer)
        renderMode = RENDERMODE_WHEN_DIRTY
    }

    /** Pass null to fall back to the bundled default look. */
    fun applyLut(lut: CubeLut?) {
        queueEvent { renderer.pendingLut = lut ?: DefaultLut.build() }
        requestRender()
    }

    private inner class PreviewRenderer : Renderer {

        private var program = 0
        private var oesTexture = 0
        private var lutTexture = 0
        private var lutSize = 0

        private var surfaceTexture: SurfaceTexture? = null
        private var previewSurface: Surface? = null

        private var uTex = 0
        private var uLut = 0
        private var uTexMatrix = 0
        private var uLutSize = 0
        private var uLutMix = 0

        private val texMatrix = FloatArray(16)
        private val quadData = floatArrayOf(-1f, -1f, 1f, -1f, -1f, 1f, 1f, 1f)
        private val quad: FloatBuffer = ByteBuffer
            .allocateDirect(quadData.size * 4)
            .order(ByteOrder.nativeOrder())
            .asFloatBuffer()
            .apply {
                put(quadData)
                position(0)
            }

        @Volatile
        var pendingLut: CubeLut? = null

        override fun onSurfaceCreated(gl: GL10?, config: EGLConfig?) {
            program = buildProgram()
            uTex = GLES30.glGetUniformLocation(program, "uTex")
            uLut = GLES30.glGetUniformLocation(program, "uLut")
            uTexMatrix = GLES30.glGetUniformLocation(program, "uTexMatrix")
            uLutSize = GLES30.glGetUniformLocation(program, "uLutSize")
            uLutMix = GLES30.glGetUniformLocation(program, "uLutMix")

            GLES30.glDisable(GLES30.GL_DEPTH_TEST)
            GLES30.glClearColor(0f, 0f, 0f, 1f)

            oesTexture = createExternalTexture()
            val texture = SurfaceTexture(oesTexture)
            texture.setOnFrameAvailableListener { requestRender() }
            surfaceTexture = texture
            val surface = Surface(texture)
            previewSurface = surface
            onPreviewSurface?.invoke(surface)

            uploadLut(DefaultLut.build())
        }

        override fun onSurfaceChanged(gl: GL10?, width: Int, height: Int) {
            GLES30.glViewport(0, 0, width, height)
        }

        override fun onDrawFrame(gl: GL10?) {
            pendingLut?.let {
                uploadLut(it)
                pendingLut = null
            }

            val texture = surfaceTexture ?: return
            try {
                texture.updateTexImage()
                texture.getTransformMatrix(texMatrix)
            } catch (ignored: Exception) {
                return
            }

            GLES30.glClear(GLES30.GL_COLOR_BUFFER_BIT)
            GLES30.glUseProgram(program)

            GLES30.glActiveTexture(GLES30.GL_TEXTURE0)
            GLES30.glBindTexture(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, oesTexture)
            GLES30.glUniform1i(uTex, 0)
            GLES30.glUniformMatrix4fv(uTexMatrix, 1, false, texMatrix, 0)

            GLES30.glActiveTexture(GLES30.GL_TEXTURE1)
            GLES30.glBindTexture(GLES30.GL_TEXTURE_3D, lutTexture)
            GLES30.glUniform1i(uLut, 1)
            GLES30.glUniform1f(uLutSize, lutSize.toFloat())
            GLES30.glUniform1f(uLutMix, if (lutEnabled) lutStrength else 0f)

            quad.position(0)
            GLES30.glEnableVertexAttribArray(0)
            GLES30.glVertexAttribPointer(0, 2, GLES30.GL_FLOAT, false, 0, quad)
            GLES30.glDrawArrays(GLES30.GL_TRIANGLE_STRIP, 0, 4)
            GLES30.glDisableVertexAttribArray(0)
        }

        private fun uploadLut(lut: CubeLut) {
            if (lutTexture == 0) {
                val ids = IntArray(1)
                GLES30.glGenTextures(1, ids, 0)
                lutTexture = ids[0]
            }
            val buffer = ByteBuffer
                .allocateDirect(lut.data.size * 4)
                .order(ByteOrder.nativeOrder())
                .asFloatBuffer()
                .apply {
                    put(lut.data)
                    position(0)
                }

            GLES30.glBindTexture(GLES30.GL_TEXTURE_3D, lutTexture)
            GLES30.glTexParameteri(
                GLES30.GL_TEXTURE_3D, GLES30.GL_TEXTURE_MIN_FILTER, GLES30.GL_LINEAR
            )
            GLES30.glTexParameteri(
                GLES30.GL_TEXTURE_3D, GLES30.GL_TEXTURE_MAG_FILTER, GLES30.GL_LINEAR
            )
            GLES30.glTexParameteri(
                GLES30.GL_TEXTURE_3D, GLES30.GL_TEXTURE_WRAP_S, GLES30.GL_CLAMP_TO_EDGE
            )
            GLES30.glTexParameteri(
                GLES30.GL_TEXTURE_3D, GLES30.GL_TEXTURE_WRAP_T, GLES30.GL_CLAMP_TO_EDGE
            )
            GLES30.glTexParameteri(
                GLES30.GL_TEXTURE_3D, GLES30.GL_TEXTURE_WRAP_R, GLES30.GL_CLAMP_TO_EDGE
            )
            GLES30.glTexImage3D(
                GLES30.GL_TEXTURE_3D, 0, GLES30.GL_RGB16F,
                lut.size, lut.size, lut.size, 0,
                GLES30.GL_RGB, GLES30.GL_FLOAT, buffer,
            )
            lutSize = lut.size
        }

        private fun createExternalTexture(): Int {
            val ids = IntArray(1)
            GLES30.glGenTextures(1, ids, 0)
            val id = ids[0]
            GLES30.glBindTexture(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, id)
            GLES30.glTexParameteri(
                GLES11Ext.GL_TEXTURE_EXTERNAL_OES, GLES30.GL_TEXTURE_MIN_FILTER, GLES30.GL_LINEAR
            )
            GLES30.glTexParameteri(
                GLES11Ext.GL_TEXTURE_EXTERNAL_OES, GLES30.GL_TEXTURE_MAG_FILTER, GLES30.GL_LINEAR
            )
            GLES30.glTexParameteri(
                GLES11Ext.GL_TEXTURE_EXTERNAL_OES, GLES30.GL_TEXTURE_WRAP_S, GLES30.GL_CLAMP_TO_EDGE
            )
            GLES30.glTexParameteri(
                GLES11Ext.GL_TEXTURE_EXTERNAL_OES, GLES30.GL_TEXTURE_WRAP_T, GLES30.GL_CLAMP_TO_EDGE
            )
            return id
        }

        private fun buildProgram(): Int {
            val vertex = compile(GLES30.GL_VERTEX_SHADER, LutShader.VERTEX)
            val fragment = compile(GLES30.GL_FRAGMENT_SHADER, LutShader.FRAGMENT)
            val program = GLES30.glCreateProgram()
            GLES30.glAttachShader(program, vertex)
            GLES30.glAttachShader(program, fragment)
            GLES30.glLinkProgram(program)
            val status = IntArray(1)
            GLES30.glGetProgramiv(program, GLES30.GL_LINK_STATUS, status, 0)
            check(status[0] == GLES30.GL_TRUE) {
                "LUT program link failed: " + GLES30.glGetProgramInfoLog(program)
            }
            GLES30.glDeleteShader(vertex)
            GLES30.glDeleteShader(fragment)
            return program
        }

        private fun compile(type: Int, source: String): Int {
            val shader = GLES30.glCreateShader(type)
            GLES30.glShaderSource(shader, source)
            GLES30.glCompileShader(shader)
            val status = IntArray(1)
            GLES30.glGetShaderiv(shader, GLES30.GL_COMPILE_STATUS, status, 0)
            check(status[0] == GLES30.GL_TRUE) {
                "Shader compile failed: " + GLES30.glGetShaderInfoLog(shader)
            }
            return shader
        }
    }
}
