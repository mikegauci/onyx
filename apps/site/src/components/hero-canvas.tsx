"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Flowing field of orange threads behind the hero, drawn with Three.js.
 *
 * Three.js is imported only after the page has loaded, and only when the visitor allows motion
 * and the device can run WebGL. Everyone else sees the static gradient underneath, which is
 * also what renders without JavaScript. Rendering pauses when the hero is off-screen or the tab
 * is hidden.
 */
export function HeroCanvas() {
  const host = useRef<HTMLDivElement>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const el = host.current;
    if (!el || typeof window.matchMedia !== "function") return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const memory = (navigator as Navigator & { deviceMemory?: number }).deviceMemory;
    if ((navigator.hardwareConcurrency ?? 4) < 2 || (memory !== undefined && memory < 2)) return;

    let disposed = false;
    let cleanup: (() => void) | undefined;

    const start = async () => {
      const THREE = await import("three");
      if (disposed) return;

      let renderer: import("three").WebGLRenderer;
      try {
        renderer = new THREE.WebGLRenderer({
          antialias: true,
          alpha: true,
          powerPreference: "low-power",
        });
      } catch {
        return; // No WebGL: keep the static gradient.
      }
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.75));
      renderer.setClearColor(0x000000, 0);
      el.appendChild(renderer.domElement);
      renderer.domElement.setAttribute("aria-hidden", "true");

      const scene = new THREE.Scene();
      const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 20);
      camera.position.set(0, 0, 3.2);

      // Each thread is a polyline across the screen; the shader moves every vertex.
      const LINES = 96;
      const POINTS = 220;
      const positions = new Float32Array(LINES * POINTS * 3);
      const indices: number[] = [];
      for (let l = 0; l < LINES; l++) {
        for (let p = 0; p < POINTS; p++) {
          const i = (l * POINTS + p) * 3;
          positions[i] = (p / (POINTS - 1)) * 2 - 1;
          positions[i + 1] = l / (LINES - 1);
          positions[i + 2] = 0;
          if (p < POINTS - 1) indices.push(l * POINTS + p, l * POINTS + p + 1);
        }
      }
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
      geometry.setIndex(indices);

      const uniforms = {
        uTime: { value: 0 },
        uAspect: { value: 1 },
        uMouse: { value: new THREE.Vector2(0, 0) },
        uColorA: { value: new THREE.Color("#ff6a1a") },
        uColorB: { value: new THREE.Color("#7a1f12") },
      };

      const material = new THREE.ShaderMaterial({
        uniforms,
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
        vertexShader: /* glsl */ `
          uniform float uTime;
          uniform float uAspect;
          uniform vec2 uMouse;
          varying float vAlpha;
          varying float vLine;
          void main() {
            float x = position.x;
            float l = position.y;
            float t = uTime * 0.22;
            float spread = mix(0.5, 2.4, 0.5 + 0.5 * sin(x * 1.4 - t * 0.8));
            float y = (l - 0.5) * 0.9 * spread;
            y += sin(x * 2.1 + t + l * 2.6) * 0.42;
            y += sin(x * 5.3 - t * 1.4 + l * 7.0) * 0.045;
            y += uMouse.y * 0.12 * (1.0 - abs(x));
            float z = cos(x * 1.7 + t * 1.1 + l * 3.4) * 0.45 + uMouse.x * 0.15 * x;
            vec3 p = vec3(x * uAspect * 1.25, y + 0.05, z);
            gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
            float edge = 1.0 - smoothstep(0.55, 1.0, abs(x));
            float band = 1.0 - abs(l - 0.5) * 1.6;
            vAlpha = edge * clamp(band, 0.12, 1.0) * mix(0.55, 1.0, spread / 2.4);
            vLine = l;
          }
        `,
        fragmentShader: /* glsl */ `
          uniform vec3 uColorA;
          uniform vec3 uColorB;
          varying float vAlpha;
          varying float vLine;
          void main() {
            vec3 c = mix(uColorB, uColorA, smoothstep(0.1, 0.7, vLine));
            gl_FragColor = vec4(c, vAlpha * 0.5);
          }
        `,
      });

      const mesh = new THREE.LineSegments(geometry, material);
      mesh.rotation.z = -0.18;
      mesh.rotation.x = -0.35;
      scene.add(mesh);

      const resize = () => {
        const { clientWidth: w, clientHeight: h } = el;
        renderer.setSize(w, h, false);
        renderer.domElement.style.width = "100%";
        renderer.domElement.style.height = "100%";
        camera.aspect = w / h;
        uniforms.uAspect.value = Math.max(w / h, 0.8);
        camera.updateProjectionMatrix();
      };
      resize();
      const ro = new ResizeObserver(resize);
      ro.observe(el);

      const target = new THREE.Vector2();
      const onPointer = (e: PointerEvent) => {
        target.set(
          (e.clientX / window.innerWidth) * 2 - 1,
          -((e.clientY / window.innerHeight) * 2 - 1),
        );
      };
      window.addEventListener("pointermove", onPointer, { passive: true });

      let visible = true;
      const io = new IntersectionObserver(([entry]) => {
        visible = !!entry?.isIntersecting;
      });
      io.observe(el);

      const timer = new THREE.Timer();
      let frame = 0;
      let first = true;
      // If the device can't hold ~25fps over the first 90 frames, stop and keep the gradient.
      let sampled = 0;
      let slowTotal = 0;
      const tick = () => {
        frame = requestAnimationFrame(tick);
        timer.update();
        if (!visible || document.hidden) return;
        const dt = timer.getDelta();
        if (sampled < 90 && !first) {
          sampled++;
          slowTotal += dt;
          if (sampled === 90 && slowTotal / sampled > 0.04) {
            setReady(false);
            cancelAnimationFrame(frame);
            return;
          }
        }
        uniforms.uTime.value += Math.min(dt, 0.05);
        uniforms.uMouse.value.lerp(target, 0.04);
        renderer.render(scene, camera);
        if (first) {
          first = false;
          setReady(true);
        }
      };
      tick();

      cleanup = () => {
        cancelAnimationFrame(frame);
        window.removeEventListener("pointermove", onPointer);
        ro.disconnect();
        io.disconnect();
        geometry.dispose();
        material.dispose();
        timer.dispose();
        renderer.dispose();
        renderer.domElement.remove();
      };
    };

    // Wait until the page is idle so the hero text paints first.
    const idle = window.requestIdleCallback ?? ((cb: () => void) => window.setTimeout(cb, 200));
    const handle = idle(() => void start());

    return () => {
      disposed = true;
      if (window.cancelIdleCallback && typeof handle === "number")
        window.cancelIdleCallback(handle);
      cleanup?.();
    };
  }, []);

  return (
    <div
      ref={host}
      aria-hidden
      className={`absolute inset-0 transition-opacity duration-[1500ms] ${ready ? "opacity-100" : "opacity-0"}`}
    />
  );
}
