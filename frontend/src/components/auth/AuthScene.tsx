"use client";

import { useEffect, useRef, useState, type MutableRefObject } from "react";
import type * as ThreeNS from "three";
import type { ThemeName } from "@/lib/theme";

export type AuthSignal = "keystroke" | "focusPassword" | "blurPassword" | "submitting" | "error" | "success" | "idle";
export type AuthView = "login" | "register";

type Three = typeof ThreeNS;

type Hooks = {
  signalRef: MutableRefObject<(event: AuthSignal) => void>;
  recolorRef: MutableRefObject<(() => void) | null>;
  goToViewRef: MutableRefObject<((view: AuthView) => void) | null>;
  viewRef: MutableRefObject<AuthView>;
};

// Documents, Web and Images: three orbits feeding one core, the way retrieval feeds the answer.
const RING_RADII = [2.4, 3.0, 3.6];
const RING_TILTS: [number, number, number][] = [[1.18, 0.0, 0.35], [1.95, 0.55, -0.4], [1.42, -0.72, 1.1]];
const RING_SPIN = [0.22, -0.16, 0.12];
const SHARDS_PER_RING = 8;
const PULSE_POOL = 6;
const TRAIL = 6;
const PULSE_TIME = 0.8;
const VIEW_TIME = 1.2;
const CAMERA_DISTANCE = 9.6;
const CAMERA_PRESETS: Record<AuthView, [number, number, number]> = {
  login: [0, 0.35, 9.6],
  register: [3.4, 1.6, 8.8],
};

// Per-theme feel. HUD glows (additive blending); Cream stays legible on a light page.
const LOOKS = {
  hud: { particles: 0.85, size: 0.075, glow: 0.55, ring: 0.6, emissive: 0.28, ambient: 0.35, lights: 1.6, coreTint: 0.6 },
  cream: { particles: 0.55, size: 0.07, glow: 0.32, ring: 0.7, emissive: 0.1, ambient: 0.6, lights: 1.25, coreTint: 1 },
};

const easeInOut = (x: number) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

function radialTexture(THREE: Three, size: number, stops: [number, string][]): ThreeNS.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext("2d");
  if (ctx) {
    const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
    for (const [offset, color] of stops) g.addColorStop(offset, color);
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, size, size);
  }
  return new THREE.CanvasTexture(canvas);
}

/** Builds the scene once and returns its teardown. Throws only if WebGL is unavailable. */
function buildScene(THREE: Three, host: HTMLDivElement, hooks: Hooks): () => void {
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const lowPower = window.innerWidth < 768 || (navigator.hardwareConcurrency || 8) <= 4;

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75));
  renderer.outputEncoding = THREE.sRGBEncoding; // r134: no outputColorSpace yet
  renderer.setClearColor(0x000000, 0);
  const canvas = renderer.domElement;
  canvas.className = "auth-canvas";
  canvas.setAttribute("aria-hidden", "true");
  host.appendChild(canvas);

  const disposables: { dispose: () => void }[] = [];
  const track = <T extends { dispose: () => void }>(item: T): T => {
    disposables.push(item);
    return item;
  };

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100);
  const system = new THREE.Group(); // core, rings, shards, pulses: what a drag rotates
  const field = new THREE.Group(); // particle backdrop
  scene.add(system, field);

  // ── palette: read from the CSS variables, so the scene follows the theme ──
  const root = document.documentElement;
  const pal = {
    accent: new THREE.Color(),
    accent2: new THREE.Color(),
    sage: new THREE.Color(),
    brick: new THREE.Color(),
    paper: new THREE.Color(),
  };
  const tints = [pal.accent, pal.accent2, pal.sage];
  const tmpColor = new THREE.Color();
  const readVar = (name: string, out: ThreeNS.Color, fallback: string) => {
    const parts = getComputedStyle(root).getPropertyValue(name).trim().split(/[\s,]+/).map(Number);
    if (parts.length >= 3 && parts.slice(0, 3).every(Number.isFinite)) out.setRGB(parts[0] / 255, parts[1] / 255, parts[2] / 255);
    else out.set(fallback);
    out.convertSRGBToLinear(); // CSS colours are sRGB; materials work in linear space
  };

  const glowTex = track(radialTexture(THREE, 128, [[0, "rgba(255,255,255,1)"], [0.22, "rgba(255,255,255,0.5)"], [1, "rgba(255,255,255,0)"]]));
  const dotTex = track(radialTexture(THREE, 64, [[0, "rgba(255,255,255,1)"], [0.45, "rgba(255,255,255,0.8)"], [1, "rgba(255,255,255,0)"]]));

  // ── core ──
  const coreMat = track(new THREE.MeshStandardMaterial({ metalness: 0.6, roughness: 0.25, flatShading: true }));
  const core = new THREE.Mesh(track(new THREE.IcosahedronGeometry(1.2, 1)), coreMat);
  const shellSource = new THREE.IcosahedronGeometry(1.55, 1);
  const shellMat = track(new THREE.LineBasicMaterial({ transparent: true, opacity: 0.5 }));
  const shell = new THREE.LineSegments(track(new THREE.EdgesGeometry(shellSource)), shellMat);
  shellSource.dispose();
  // Bloom post-processing would break the transparent canvas, so the glow is a sprite.
  const glowMat = track(new THREE.SpriteMaterial({ map: glowTex, transparent: true, depthWrite: false }));
  const glow = new THREE.Sprite(glowMat);
  glow.scale.setScalar(5.2);
  system.add(core, shell, glow);

  // ── orbit rings ──
  const ringPivots: ThreeNS.Group[] = [];
  const ringMeshes: ThreeNS.Mesh[] = [];
  const ringMats: ThreeNS.MeshBasicMaterial[] = [];
  RING_RADII.forEach((radius, i) => {
    const pivot = new THREE.Group();
    pivot.rotation.set(...RING_TILTS[i]);
    const mat = track(new THREE.MeshBasicMaterial({ transparent: true, depthWrite: false }));
    const mesh = new THREE.Mesh(track(new THREE.TorusGeometry(radius, 0.008, 6, 200)), mat);
    pivot.add(mesh);
    system.add(pivot);
    ringPivots.push(pivot);
    ringMeshes.push(mesh);
    ringMats.push(mat);
  });

  // ── shards: 24 cards in one InstancedMesh ──
  const SHARDS = RING_RADII.length * SHARDS_PER_RING;
  const shardMat = track(new THREE.MeshStandardMaterial({ metalness: 0.15, roughness: 0.45, transparent: true, opacity: 0.92 }));
  const shards = new THREE.InstancedMesh(track(new THREE.BoxGeometry(0.28, 0.36, 0.02)), shardMat, SHARDS);
  shards.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  system.add(shards);
  const shardRing = new Uint8Array(SHARDS);
  const shardAngle = new Float32Array(SHARDS);
  const shardSpeed = new Float32Array(SHARDS);
  const shardPhase = new Float32Array(SHARDS * 3);
  const shardPos = Array.from({ length: SHARDS }, () => new THREE.Vector3());
  for (let i = 0; i < SHARDS; i++) {
    const ring = Math.floor(i / SHARDS_PER_RING);
    shardRing[i] = ring;
    shardAngle[i] = ((i % SHARDS_PER_RING) / SHARDS_PER_RING) * Math.PI * 2 + Math.random() * 0.4;
    shardSpeed[i] = (0.1 + Math.random() * 0.12) * (ring % 2 === 0 ? 1 : -1);
    shardPhase[i * 3] = Math.random() * Math.PI * 2;
    shardPhase[i * 3 + 1] = Math.random() * Math.PI * 2;
    shardPhase[i * 3 + 2] = Math.random() * Math.PI * 2;
  }

  // ── particle field: a spherical shell, kept clear of the camera so no dot fills the screen ──
  const COUNT = lowPower ? 500 : 1200;
  const positions = new Float32Array(COUNT * 3);
  const keepClear = [new THREE.Vector3(...CAMERA_PRESETS.login), new THREE.Vector3(...CAMERA_PRESETS.register)];
  const probe = new THREE.Vector3();
  for (let i = 0; i < COUNT; i++) {
    do {
      const u = Math.random() * 2 - 1;
      const theta = Math.random() * Math.PI * 2;
      const r = 6 + Math.random() * 8;
      const s = Math.sqrt(1 - u * u);
      probe.set(r * s * Math.cos(theta), r * u, r * s * Math.sin(theta));
    } while (keepClear.some((c) => c.distanceTo(probe) < 4.8));
    positions[i * 3] = probe.x;
    positions[i * 3 + 1] = probe.y;
    positions[i * 3 + 2] = probe.z;
  }
  const pointsGeo = track(new THREE.BufferGeometry());
  pointsGeo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  const pointsMat = track(new THREE.PointsMaterial({ map: dotTex, transparent: true, depthWrite: false, sizeAttenuation: true }));
  field.add(new THREE.Points(pointsGeo, pointsMat));

  // ── retrieval pulses: a fixed pool, reused ──
  const pulseGeo = track(new THREE.SphereGeometry(0.065, 12, 12));
  const pulseMat = track(new THREE.MeshBasicMaterial({ transparent: true, depthWrite: false }));
  const headGlowMat = track(new THREE.SpriteMaterial({ map: glowTex, transparent: true, depthWrite: false, opacity: 0.9 }));
  const trailMats = Array.from({ length: TRAIL }, (_, k) =>
    track(new THREE.SpriteMaterial({ map: dotTex, transparent: true, depthWrite: false, opacity: 0.75 * (1 - (k + 1) / (TRAIL + 1)) })),
  );
  type Pulse = { head: ThreeNS.Mesh; trail: ThreeNS.Sprite[]; curve: ThreeNS.QuadraticBezierCurve3; t: number; active: boolean };
  const pool: Pulse[] = [];
  for (let p = 0; p < PULSE_POOL; p++) {
    const head = new THREE.Mesh(pulseGeo, pulseMat);
    const halo = new THREE.Sprite(headGlowMat);
    halo.scale.setScalar(0.6);
    head.add(halo);
    head.visible = false;
    system.add(head);
    const trail = trailMats.map((mat, k) => {
      const s = new THREE.Sprite(mat);
      s.scale.setScalar(0.16 * (1 - (k / TRAIL) * 0.6));
      s.visible = false;
      system.add(s);
      return s;
    });
    pool.push({ head, trail, curve: new THREE.QuadraticBezierCurve3(new THREE.Vector3(), new THREE.Vector3(), new THREE.Vector3()), t: 0, active: false });
  }

  // ── click shockwave ──
  const waveMat = track(new THREE.MeshBasicMaterial({ transparent: true, depthWrite: false, side: THREE.DoubleSide, opacity: 0 }));
  const wave = new THREE.Mesh(track(new THREE.RingGeometry(0.96, 1.0, 96)), waveMat);
  wave.visible = false;
  scene.add(wave);

  // ── lights ──
  const ambient = new THREE.AmbientLight(0xffffff, 0.5);
  const keyLight = new THREE.PointLight(0xffffff, 1.3, 0);
  const rimLight = new THREE.PointLight(0xffffff, 1.1, 0);
  scene.add(ambient, keyLight, rimLight);

  // ── theme: recolour in place, never rebuild ──
  let look = LOOKS.cream;
  const blended: { blending: ThreeNS.Blending; needsUpdate: boolean }[] = [glowMat, pointsMat, pulseMat, headGlowMat, waveMat, ...trailMats];
  const applyTheme = () => {
    const hud = root.dataset.theme === "hud";
    look = hud ? LOOKS.hud : LOOKS.cream;
    readVar("--brass-500", pal.accent, "#a97a3a");
    readVar("--brass-300", pal.accent2, "#d4ad68");
    readVar("--sage-500", pal.sage, "#4c7a52");
    readVar("--brick-500", pal.brick, "#b0463e");
    readVar("--cream-100", pal.paper, "#f7f2e7");

    // Additive blending reads as neon on black but washes out to white on parchment.
    const blending = hud ? THREE.AdditiveBlending : THREE.NormalBlending;
    for (const m of blended) {
      if (m.blending !== blending) {
        m.blending = blending;
        m.needsUpdate = true;
      }
    }
    coreMat.color.copy(pal.accent).multiplyScalar(look.coreTint);
    coreMat.emissive.copy(pal.accent);
    shellMat.color.copy(hud ? pal.accent2 : pal.accent);
    glowMat.color.copy(pal.accent);
    ringMats.forEach((m, i) => m.color.copy(tints[i]));
    for (let i = 0; i < SHARDS; i++) {
      // Cream shards read as paper cards tinted by their orbit; HUD ones glow in the tint itself.
      tmpColor.copy(tints[shardRing[i]]).lerp(pal.paper, hud ? 0 : 0.45);
      shards.setColorAt(i, tmpColor);
    }
    if (shards.instanceColor) shards.instanceColor.needsUpdate = true;
    shardMat.emissive.copy(pal.accent).multiplyScalar(hud ? 0.22 : 0);
    pointsMat.color.copy(pal.accent).multiplyScalar(hud ? 1 : 0.72);
    pulseMat.color.copy(pal.accent);
    headGlowMat.color.copy(pal.accent);
    trailMats.forEach((m) => m.color.copy(pal.accent));
    waveMat.color.copy(pal.accent);
    keyLight.color.copy(pal.accent);
    rimLight.color.copy(pal.accent2);
    ambient.intensity = look.ambient;
    keyLight.intensity = rimLight.intensity = look.lights;
    pointsMat.size = look.size;
    if (reduced) render();
  };

  // ── state the loop reads; the forms write it through signal() ──
  let time = 0;
  const pointer = new THREE.Vector2();
  const ndc = new THREE.Vector2();
  const raycaster = new THREE.Raycaster();
  let ndcDirty = false;
  let overCanvas = false;
  let hovered = false;
  let dragging = false;
  let dragDX = 0;
  let dragDY = 0;
  let velY = 0;
  let velX = 0;
  let downX = 0;
  let downY = 0;
  let lastX = 0;
  let lastY = 0;
  let downId = -1;
  let downOnCore = false;
  let ringBoost = 1;
  let submitting = false;
  let privacy = 0;
  let privacyTarget = 0;
  let flash = 0;
  let bump = 0;
  let errorT = 0;
  let shakeT = 0;
  let success = -1;
  let spawnIn = 0.6;
  let lastKeystroke = -Infinity;
  let waveT = -1;
  let coreScale = 1;
  let fit = 1;

  const origin = new THREE.Vector3();
  const basePos = new THREE.Vector3(...CAMERA_PRESETS[hooks.viewRef.current]);
  const fromPos = new THREE.Vector3();
  const toPos = basePos.clone();
  let viewT = 1;
  const desired = new THREE.Vector3();
  const dollyTarget = new THREE.Vector3();
  const local = new THREE.Vector3();
  const unit = new THREE.Vector3(1, 1, 1);
  const euler = new THREE.Euler();
  const quat = new THREE.Quaternion();
  const matrix = new THREE.Matrix4();
  camera.position.copy(basePos);
  camera.lookAt(origin);

  const spawnPulse = () => {
    for (const p of pool) {
      if (p.active) continue;
      const from = shardPos[Math.floor(Math.random() * SHARDS)];
      p.curve.v0.copy(from);
      p.curve.v1.copy(from).multiplyScalar(0.5);
      p.curve.v1.y += 0.9 + Math.random() * 0.6;
      p.curve.v1.z += (Math.random() - 0.5) * 1.2;
      p.curve.v2.set(0, 0, 0);
      p.t = 0;
      p.active = true;
      p.head.position.copy(from);
      p.head.visible = true;
      return;
    }
  };

  const burst = () => {
    waveT = 0;
    wave.visible = true;
    spawnPulse();
    spawnPulse();
    spawnPulse();
  };

  const step = (dt: number) => {
    time += dt;
    const ease = (rate: number) => 1 - Math.exp(-rate * dt); // frame-rate independent lerp

    if (viewT < 1) {
      viewT = Math.min(1, viewT + dt / VIEW_TIME);
      basePos.lerpVectors(fromPos, toPos, easeInOut(viewT));
    }

    // Drag rotates the system; when released it coasts and slows (~0.92 per 60 Hz frame).
    if (dragging) {
      system.rotation.y += dragDX * 0.006;
      system.rotation.x = clamp(system.rotation.x + dragDY * 0.004, -0.7, 0.7);
      velY = dt > 0 ? (dragDX * 0.006) / dt : 0;
      velX = dt > 0 ? (dragDY * 0.004) / dt : 0;
      dragDX = dragDY = 0;
    } else {
      system.rotation.y += velY * dt;
      system.rotation.x = clamp(system.rotation.x + velX * dt, -0.7, 0.7);
      const decay = Math.pow(0.92, dt * 60);
      velY *= decay;
      velX *= decay;
    }
    system.rotation.y += dt * 0.05;

    ringBoost += ((submitting ? 3 : 1) - ringBoost) * ease(4);
    privacy += (privacyTarget - privacy) * ease(5);
    flash = Math.max(0, flash - dt * 2.2);
    bump = Math.max(0, bump - dt * 4);
    errorT = Math.max(0, errorT - dt);
    shakeT = Math.max(0, shakeT - dt);

    // core
    const spin = hovered ? 2 : 1;
    core.rotation.y += dt * 0.32 * spin;
    core.rotation.x += dt * 0.12 * spin;
    shell.rotation.y -= dt * 0.2 * spin;
    shell.rotation.z += dt * 0.07;
    coreScale += ((hovered ? 1.08 : 1) + bump * 0.06 + flash * 0.05 - coreScale) * ease(10);
    core.scale.setScalar(coreScale);
    const err = errorT > 0 ? Math.min(1, errorT / 0.25) : 0; // full red, then fades out over the last 250 ms
    coreMat.emissive.copy(pal.accent).lerp(pal.brick, err);
    coreMat.emissiveIntensity = look.emissive + flash * 0.9 + bump * 0.35 + err * 1.2;
    glowMat.color.copy(pal.accent).lerp(pal.brick, err);
    glowMat.opacity = look.glow * (1 + flash * 0.6 + err * 0.5);
    glow.scale.setScalar(5.2 * (1 + flash * 0.18 + bump * 0.08));

    // lights orbit slowly
    keyLight.position.set(Math.cos(time * 0.35) * 5, 2.5, Math.sin(time * 0.35) * 5);
    rimLight.position.set(Math.cos(time * 0.27 + 2.6) * -5, -1.8, Math.sin(time * 0.27 + 2.6) * 5);

    // rings tighten ~8% in privacy mode
    const ringScale = 1 - 0.08 * privacy;
    for (let i = 0; i < ringPivots.length; i++) {
      ringMeshes[i].rotation.z += dt * RING_SPIN[i] * ringBoost;
      ringPivots[i].scale.setScalar(ringScale);
      ringPivots[i].updateMatrix();
      ringMats[i].opacity = look.ring * (1 - 0.3 * privacy);
    }

    // shards orbit their ring and tumble
    for (let i = 0; i < SHARDS; i++) {
      shardAngle[i] += dt * shardSpeed[i] * ringBoost;
      const radius = RING_RADII[shardRing[i]];
      local.set(Math.cos(shardAngle[i]) * radius, Math.sin(shardAngle[i]) * radius, 0).applyMatrix4(ringPivots[shardRing[i]].matrix);
      shardPos[i].copy(local);
      euler.set(shardPhase[i * 3] + time * 0.5, shardPhase[i * 3 + 1] + time * 0.35, shardPhase[i * 3 + 2]);
      quat.setFromEuler(euler);
      matrix.compose(local, quat, unit);
      shards.setMatrixAt(i, matrix);
    }
    shards.instanceMatrix.needsUpdate = true;

    // retrieval pulses: shard -> core along a curve, with a short fading trail
    spawnIn -= dt;
    if (spawnIn <= 0) {
      spawnPulse();
      spawnIn = submitting ? 0.16 : 1.4;
    }
    for (const p of pool) {
      if (!p.active) continue;
      p.t += dt / PULSE_TIME;
      if (p.t >= 1) {
        p.active = false;
        p.head.visible = false;
        for (const s of p.trail) s.visible = false;
        flash = 1; // the core lights up as the "retrieved" pulse arrives
        continue;
      }
      p.curve.getPoint(p.t * p.t, p.head.position);
      for (let k = 0; k < TRAIL; k++) {
        const tk = p.t - (k + 1) * 0.045;
        const s = p.trail[k];
        s.visible = tk > 0;
        if (tk > 0) p.curve.getPoint(tk * tk, s.position);
      }
    }

    // particles: slow drift, dim in privacy mode, stretch outward on success (warp)
    field.rotation.y = Math.sin(time * 0.045) * 0.18;
    field.rotation.x = Math.sin(time * 0.03) * 0.06;
    if (success >= 0) success = Math.min(1, success + dt / 0.7);
    const warp = success >= 0 ? success * success : 0;
    field.scale.setScalar(1 + warp * 1.6);
    pointsMat.size = look.size * (1 + warp * 2.5);
    pointsMat.opacity = look.particles * (1 - 0.6 * privacy);

    // camera: preset angle + pointer parallax (+ dolly into the core on success, + shake on error)
    desired.copy(basePos);
    desired.x += pointer.x * 0.6;
    desired.y += pointer.y * 0.6;
    if (warp > 0) {
      dollyTarget.copy(basePos).setLength(2.9).add(system.position);
      desired.lerp(dollyTarget, warp);
    }
    camera.position.lerp(desired, ease(3.2 + warp * 12));
    if (shakeT > 0) {
      const a = 0.2 * (shakeT / 0.3);
      camera.position.x += (Math.random() - 0.5) * a;
      camera.position.y += (Math.random() - 0.5) * a;
    }
    camera.lookAt(origin);

    if (waveT >= 0) {
      waveT += dt / 0.9;
      if (waveT >= 1) {
        waveT = -1;
        wave.visible = false;
      } else {
        wave.position.copy(system.position);
        wave.quaternion.copy(camera.quaternion);
        wave.scale.setScalar((1.3 + waveT * 3.8) * fit);
        waveMat.opacity = 0.85 * (1 - waveT);
      }
    }

    // hover: raycast against the core only, and only when the pointer is on the canvas itself
    if (ndcDirty) {
      ndcDirty = false;
      if (overCanvas && !dragging) {
        raycaster.setFromCamera(ndc, camera);
        hovered = raycaster.intersectObject(core, false).length > 0;
      } else {
        hovered = false;
      }
      canvas.style.cursor = hovered ? "pointer" : dragging ? "grabbing" : "grab";
    }
  };

  const render = () => renderer.render(scene, camera);

  // ── sizing ──
  const resize = () => {
    const w = host.clientWidth || window.innerWidth;
    const h = host.clientHeight || window.innerHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    // Shrink the system on narrow screens so the outer ring stays in view.
    const halfW = Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) * CAMERA_DISTANCE * camera.aspect;
    fit = Math.min(1, (halfW * 0.92) / 3.9);
    system.scale.setScalar(fit);
    // Desktop: between the hero and the card. Mobile: centred behind the card.
    system.position.set(w >= 1024 ? 0.55 : 0, w >= 1024 ? 0.1 : 0, 0);
    if (reduced) render();
  };
  const resizeObserver = new ResizeObserver(resize);
  resizeObserver.observe(host);
  resize();

  // ── input ──
  const toNdc = (e: PointerEvent) => {
    ndc.set((e.clientX / window.innerWidth) * 2 - 1, -((e.clientY / window.innerHeight) * 2 - 1));
  };
  const onPointerMove = (e: PointerEvent) => {
    pointer.set((e.clientX / window.innerWidth) * 2 - 1, -((e.clientY / window.innerHeight) * 2 - 1));
    toNdc(e);
    ndcDirty = true;
    overCanvas = e.target === canvas;
    if (dragging && e.pointerId === downId) {
      dragDX += e.clientX - lastX;
      dragDY += e.clientY - lastY;
      lastX = e.clientX;
      lastY = e.clientY;
    }
  };
  const onPointerDown = (e: PointerEvent) => {
    if (e.pointerType === "mouse" && e.button !== 0) return;
    downX = lastX = e.clientX;
    downY = lastY = e.clientY;
    downId = e.pointerId;
    toNdc(e);
    raycaster.setFromCamera(ndc, camera); // touch has no hover, so test the core here
    downOnCore = raycaster.intersectObject(core, false).length > 0;
    if (!downOnCore) {
      dragging = true;
      velX = velY = 0;
      canvas.setPointerCapture?.(e.pointerId);
    }
    ndcDirty = true;
  };
  const onPointerUp = (e: PointerEvent) => {
    if (e.pointerId !== downId) return;
    if (e.type === "pointerup" && downOnCore && Math.hypot(e.clientX - downX, e.clientY - downY) < 8) burst();
    dragging = false;
    downOnCore = false;
    downId = -1;
    ndcDirty = true;
  };

  // ── loop ──
  const clock = new THREE.Clock();
  let raf = 0;
  const frame = () => {
    raf = requestAnimationFrame(frame);
    step(Math.min(clock.getDelta(), 0.05));
    render();
  };
  const onVisibility = () => {
    if (document.hidden) {
      cancelAnimationFrame(raf);
      raf = 0;
    } else if (!raf) {
      clock.getDelta(); // drop the time spent hidden
      raf = requestAnimationFrame(frame);
    }
  };

  applyTheme();
  hooks.recolorRef.current = applyTheme;
  hooks.goToViewRef.current = (view) => {
    fromPos.copy(basePos);
    toPos.set(...CAMERA_PRESETS[view]);
    if (reduced) {
      basePos.copy(toPos);
      camera.position.copy(basePos);
      camera.lookAt(origin);
      render();
    } else {
      viewT = 0;
    }
  };

  if (reduced) {
    // One static frame: no loop, parallax, drag or signals.
    step(0);
    render();
  } else {
    hooks.signalRef.current = (event) => {
      switch (event) {
        case "keystroke": {
          const now = performance.now();
          if (now - lastKeystroke >= 120) {
            lastKeystroke = now;
            bump = 1;
            spawnPulse();
          }
          break;
        }
        case "focusPassword":
          privacyTarget = 1;
          break;
        case "blurPassword":
          privacyTarget = 0;
          break;
        case "submitting":
          submitting = true;
          spawnIn = 0;
          break;
        case "error":
          submitting = false;
          errorT = 0.6;
          shakeT = 0.3;
          break;
        case "success":
          submitting = false;
          privacyTarget = 0;
          success = 0;
          break;
        case "idle":
          submitting = false;
          break;
      }
    };
    canvas.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("pointermove", onPointerMove, { passive: true });
    window.addEventListener("pointerup", onPointerUp);
    window.addEventListener("pointercancel", onPointerUp);
    document.addEventListener("visibilitychange", onVisibility);
    if (!document.hidden) raf = requestAnimationFrame(frame);
  }

  return () => {
    cancelAnimationFrame(raf);
    raf = 0;
    resizeObserver.disconnect();
    canvas.removeEventListener("pointerdown", onPointerDown);
    window.removeEventListener("pointermove", onPointerMove);
    window.removeEventListener("pointerup", onPointerUp);
    window.removeEventListener("pointercancel", onPointerUp);
    document.removeEventListener("visibilitychange", onVisibility);
    hooks.signalRef.current = () => {};
    hooks.recolorRef.current = null;
    hooks.goToViewRef.current = null;
    for (const item of disposables) item.dispose();
    renderer.dispose();
    renderer.forceContextLoss();
    canvas.remove();
  };
}

/**
 * The "Knowledge Core" behind the Login/Register card: documents, web pages and images orbit a
 * glowing core and stream into it. Raw Three.js r134 (vanta@0.5.24 pins `three`, so no
 * react-three-fiber/drei), loaded lazily like VantaBackground. Set up once; theme, view and form
 * signals reach the running loop through refs. It unmounts when the user enters the app, so
 * nothing keeps rendering next to the Vanta background and local LLM inference.
 */
export default function AuthScene({
  theme,
  view,
  signalRef,
}: {
  theme: ThemeName;
  view: AuthView;
  signalRef: MutableRefObject<(event: AuthSignal) => void>;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const recolorRef = useRef<(() => void) | null>(null);
  const goToViewRef = useRef<((view: AuthView) => void) | null>(null);
  const viewRef = useRef<AuthView>(view);
  const [fallback, setFallback] = useState(false);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    let cancelled = false;
    let teardown: (() => void) | null = null;

    (async () => {
      try {
        const THREE = await import("three");
        if (cancelled) return;
        teardown = buildScene(THREE, host, { signalRef, recolorRef, goToViewRef, viewRef });
      } catch (err) {
        // WebGL unavailable (software rendering, old driver): the CSS fallback takes over.
        console.warn("3D login scene unavailable, using the CSS fallback:", err);
        if (!cancelled) setFallback(true);
      }
    })();

    return () => {
      cancelled = true;
      teardown?.();
    };
  }, [signalRef]);

  // Recolour live when the theme changes (the CSS variables have already flipped).
  useEffect(() => {
    recolorRef.current?.();
  }, [theme]);

  // /login <-> /register: glide the camera; the canvas stays mounted in the (auth) layout.
  useEffect(() => {
    viewRef.current = view;
    goToViewRef.current?.(view);
  }, [view]);

  return (
    <div ref={hostRef} aria-hidden="true" className="auth-canvas-layer">
      {fallback && (
        <div className="auth-fallback">
          <span className="auth-blob auth-blob-a" />
          <span className="auth-blob auth-blob-b" />
          <span className="auth-blob auth-blob-c" />
        </div>
      )}
    </div>
  );
}
