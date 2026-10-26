import math
import random
import asyncio
from typing import List, Tuple

# Advanced Anti-Fingerprinting Stealth Script injected into all browser pages
STEALTH_EVASION_SCRIPT = """
(() => {
    // 1. Delete and mask navigator.webdriver
    try {
        const newProto = Object.getPrototypeOf(navigator);
        delete newProto.webdriver;
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined,
            configurable: true
        });
    } catch (e) {}

    // 2. Realistic window.chrome object
    window.chrome = {
        app: {
            isInstalled: false,
            InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' },
            RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' }
        },
        runtime: {
            OnInstalledReason: { CHROME_UPDATE: 'chrome_update', INSTALL: 'install', SHARED_MODULE_UPDATE: 'shared_module_update', UPDATE: 'update' },
            OnRestartRequiredReason: { APP_UPDATE: 'app_update', OS_UPDATE: 'os_update', PERIODIC: 'periodic' },
            PlatformArch: { ARM: 'arm', ARM64: 'arm64', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' },
            PlatformNaclArch: { ARM: 'arm', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' },
            PlatformOs: { ANDROID: 'android', CROS: 'cros', LINUX: 'linux', MAC: 'mac', OPENBSD: 'openbsd', WIN: 'win' },
            RequestUpdateCheckStatus: { NO_UPDATE: 'no_update', THROTTLED: 'throttled', UPDATE_AVAILABLE: 'update_available' }
        },
        csi: function() {},
        loadTimes: function() {}
    };

    // 3. WebGL Vendor and Renderer Spoofing (Emulates real NVIDIA GeForce RTX GPU)
    const getParameterProxyHandler = {
        apply: function(target, ctx, args) {
            const param = args[0];
            // UNMASKED_VENDOR_WEBGL
            if (param === 37445) {
                return 'Google Inc. (NVIDIA)';
            }
            // UNMASKED_RENDERER_WEBGL
            if (param === 37446) {
                return 'ANGLE (NVIDIA, NVIDIA GeForce RTX 4090 (0x00002684) Direct3D11 vs_5_0 ps_5_0, D3D11)';
            }
            return Reflect.apply(target, ctx, args);
        }
    };

    try {
        const WebGLRenderingContextProto = WebGLRenderingContext.prototype;
        WebGLRenderingContextProto.getParameter = new Proxy(WebGLRenderingContextProto.getParameter, getParameterProxyHandler);
        if (typeof WebGL2RenderingContext !== 'undefined') {
            const WebGL2RenderingContextProto = WebGL2RenderingContext.prototype;
            WebGL2RenderingContextProto.getParameter = new Proxy(WebGL2RenderingContextProto.getParameter, getParameterProxyHandler);
        }
    } catch (e) {}

    // 4. Subtle Canvas Noise Injection (Defeats canvas fingerprinting without corrupting images)
    try {
        const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
        HTMLCanvasElement.prototype.toDataURL = function(type) {
            const ctx = this.getContext('2d');
            if (ctx && this.width > 0 && this.height > 0) {
                try {
                    const imgData = ctx.getImageData(0, 0, Math.min(this.width, 10), Math.min(this.height, 10));
                    // Subtle noise on least significant bit
                    for (let i = 0; i < imgData.data.length; i += 4) {
                        imgData.data[i] = imgData.data[i] ^ (Math.random() < 0.05 ? 1 : 0);
                    }
                    ctx.putImageData(imgData, 0, 0);
                } catch (err) {}
            }
            return originalToDataURL.apply(this, arguments);
        };
    } catch (e) {}

    // 5. AudioContext Fingerprint Noise
    try {
        const AudioContext = window.AudioContext || window.webkitAudioContext;
        if (AudioContext) {
            const origGetChannelData = AudioBuffer.prototype.getChannelData;
            AudioBuffer.prototype.getChannelData = function() {
                const results = origGetChannelData.apply(this, arguments);
                for (let i = 0; i < results.length; i += 100) {
                    results[i] = results[i] + (Math.random() * 0.0000001);
                }
                return results;
            };
        }
    } catch (e) {}

    // 6. Realistic Plugins & MimeTypes
    try {
        Object.defineProperty(navigator, 'plugins', {
            get: () => {
                return [
                    { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
                    { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
                    { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' }
                ];
            }
        });
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en']
        });
        Object.defineProperty(navigator, 'hardwareConcurrency', {
            get: () => 16
        });
        Object.defineProperty(navigator, 'deviceMemory', {
            get: () => 8
        });
    } catch (e) {}

    // 7. Notification Permission Query Spoofing
    try {
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );
    } catch (e) {}
})();
"""

def generate_bezier_curve(start: Tuple[float, float], end: Tuple[float, float], num_points: int = 25) -> List[Tuple[float, float]]:
    """
    Generates natural human-like mouse cursor trajectory using cubic Bézier curves
    with randomized control points and physiological micro-jitters.
    """
    x0, y0 = start
    x3, y3 = end

    # Compute random intermediate control points with realistic human hand deviation
    dx = x3 - x0
    dy = y3 - y0
    dist = math.hypot(dx, dy)

    deviation = min(dist * 0.3, 100)
    ctrl1_x = x0 + dx * random.uniform(0.2, 0.4) + random.uniform(-deviation, deviation)
    ctrl1_y = y0 + dy * random.uniform(0.1, 0.3) + random.uniform(-deviation, deviation)

    ctrl2_x = x0 + dx * random.uniform(0.6, 0.8) + random.uniform(-deviation, deviation)
    ctrl2_y = y0 + dy * random.uniform(0.7, 0.9) + random.uniform(-deviation, deviation)

    points = []
    for i in range(num_points + 1):
        t = i / num_points
        # Ease-in-out curve for human acceleration & deceleration
        t_eased = t * t * (3.0 - 2.0 * t)

        # Cubic Bezier formula
        u = 1 - t_eased
        tt = t_eased * t_eased
        uu = u * u
        uuu = uu * u
        ttt = tt * t_eased

        px = uuu * x0 + 3 * uu * t_eased * ctrl1_x + 3 * u * tt * ctrl2_x + ttt * x3
        py = uuu * y0 + 3 * uu * t_eased * ctrl1_y + 3 * u * tt * ctrl2_y + ttt * y3

        # Add physiological hand micro-tremor (0.5 to 1.5 pixels)
        if 0 < i < num_points:
            px += random.uniform(-0.8, 0.8)
            py += random.uniform(-0.8, 0.8)

        points.append((round(px, 1), round(py, 1)))

    return points
