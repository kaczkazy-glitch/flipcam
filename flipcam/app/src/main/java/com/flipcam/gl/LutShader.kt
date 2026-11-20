package com.flipcam.gl

/** GLSL ES 3.0 sources for the LUT preview pass. */
object LutShader {

    const val VERTEX = """
        #version 300 es
        uniform mat4 uTexMatrix;
        layout(location = 0) in vec2 aPos;
        out vec2 vUv;

        void main() {
            vUv = (uTexMatrix * vec4(aPos * 0.5 + 0.5, 0.0, 1.0)).xy;
            gl_Position = vec4(aPos, 0.0, 1.0);
        }
    """

    /**
     * The recorded stream never passes through here: Camera2 writes Log/HLG frames straight to
     * the encoder surface. Only the viewfinder texture is graded.
     */
    const val FRAGMENT = """
        #version 300 es
        #extension GL_OES_EGL_image_external_essl3 : require
        precision highp float;
        precision highp sampler3D;

        uniform samplerExternalOES uTex;
        uniform sampler3D uLut;
        uniform float uLutSize;
        uniform float uLutMix;
        in vec2 vUv;
        out vec4 fragColor;

        void main() {
            vec4 src = texture(uTex, vUv);
            vec3 base = clamp(src.rgb, 0.0, 1.0);

            // Sample the LUT at texel centres so edges do not bleed into neighbouring cells.
            float scale = (uLutSize - 1.0) / uLutSize;
            float offset = 0.5 / uLutSize;
            vec3 graded = texture(uLut, base * scale + offset).rgb;

            fragColor = vec4(mix(base, graded, uLutMix), 1.0);
        }
    """
}
