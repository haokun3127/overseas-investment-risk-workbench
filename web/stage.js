'use strict';
// Sign-in light field: one full-screen triangle and one fragment shader, no libraries.
// Abstract procedural field only — it does not depict coastlines, borders or live data.
(() => {
  const VERTEX = 'attribute vec2 p;void main(){gl_Position=vec4(p,0.,1.);}';
  const FRAGMENT = `precision mediump float;
uniform vec2 r;uniform float t;uniform vec2 b[5];
float h(vec2 q){q=fract(q*vec2(123.34,456.21));q+=dot(q,q+45.32);return fract(q.x*q.y);}
float n(vec2 q){vec2 i=floor(q),f=fract(q),u=f*f*(3.-2.*f);
return mix(mix(h(i),h(i+vec2(1.,0.)),u.x),mix(h(i+vec2(0.,1.)),h(i+vec2(1.,1.)),u.x),u.y);}
float fbm(vec2 q){float v=0.,a=.5;for(int i=0;i<3;i++){v+=a*n(q);q=q*2.03+vec2(1.7,9.2);a*=.5;}return v;}
void main(){
vec2 uv=gl_FragCoord.xy/r;float k=r.x/r.y;vec2 q=vec2(uv.x*k,uv.y);
vec3 tide=vec3(.24,.81,.75);vec3 brass=vec3(.93,.83,.6);
float w=fbm(vec2(q.x*1.3+t*.012*6.,q.y*2.1-t*.018));
float band=smoothstep(.34,0.,abs(uv.y-.74-(w-.5)*.34));
vec3 c=mix(tide,brass,smoothstep(.15,.95,uv.x+(w-.5)*.5))*band*.35*(.55+.45*w);
float d=fbm(q*2.4+vec2(0.,t*.006));float iso=abs(fract(d*8.)-.5);
c+=tide*smoothstep(.045,0.,iso)*smoothstep(.3,.95,uv.y)*.1;
for(int i=0;i<5;i++){vec2 o=(uv-b[i])*vec2(k,1.);float l=length(o);
float ph=fract(t/3.2+float(i)*.217);float ring=smoothstep(.0045,0.,abs(l-ph*.11))*(1.-ph)*(1.-ph);
c+=tide*(ring*.55+smoothstep(.007,0.,l)*.9+smoothstep(.05,0.,l)*.12);}
gl_FragColor=vec4(c,1.);}`;
  const BEACONS = [0.18, 0.72, 0.34, 0.8, 0.5, 0.66, 0.66, 0.76, 0.82, 0.7];
  let current = null;

  function eligible() {
    const memory = navigator.deviceMemory;
    const cores = navigator.hardwareConcurrency;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches || window.innerWidth <= 900) {
      return false;
    }
    return !(memory && memory <= 4) && !(cores && cores <= 4);
  }

  function compile(gl, type, source) {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    return gl.getShaderParameter(shader, gl.COMPILE_STATUS) ? shader : null;
  }

  function unmount() {
    if (!current) {
      return;
    }
    const { canvas, gl, observers, frame, onVisibility } = current;
    cancelAnimationFrame(frame.id);
    observers.forEach((observer) => observer.disconnect());
    document.removeEventListener('visibilitychange', onVisibility);
    gl.getExtension('WEBGL_lose_context')?.loseContext();
    canvas.remove();
    current = null;
  }

  function mount(host) {
    if (!host || current?.host === host) {
      return;
    }
    unmount();
    host.dataset.stage = 'static';
    if (!eligible()) {
      return;
    }
    const canvas = document.createElement('canvas');
    canvas.className = 'auth-stage-gl';
    canvas.setAttribute('aria-hidden', 'true');
    const gl = canvas.getContext('webgl', {
      antialias: false, alpha: false, depth: false, stencil: false,
      powerPreference: 'low-power', failIfMajorPerformanceCaveat: true, preserveDrawingBuffer: false,
    });
    if (!gl) {
      return;
    }
    const vs = compile(gl, gl.VERTEX_SHADER, VERTEX);
    const fs = compile(gl, gl.FRAGMENT_SHADER, FRAGMENT);
    const program = gl.createProgram();
    if (!vs || !fs) {
      return;
    }
    gl.attachShader(program, vs);
    gl.attachShader(program, fs);
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      return;
    }
    gl.useProgram(program);
    const buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    const position = gl.getAttribLocation(program, 'p');
    gl.enableVertexAttribArray(position);
    gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);
    const uRes = gl.getUniformLocation(program, 'r');
    const uTime = gl.getUniformLocation(program, 't');
    gl.uniform2fv(gl.getUniformLocation(program, 'b'), new Float32Array(BEACONS));
    host.prepend(canvas);

    const frame = { id: 0, last: 0, visible: true, onScreen: true };
    const begin = performance.now();
    const draw = (now) => {
      frame.id = 0;
      if (!frame.visible || !frame.onScreen) {
        return;
      }
      frame.id = requestAnimationFrame(draw);
      if (now - frame.last < 33) {
        return;
      }
      frame.last = now;
      gl.uniform1f(uTime, (now - begin) / 1000);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    };
    const resume = () => {
      if (!frame.id && frame.visible && frame.onScreen) {
        frame.id = requestAnimationFrame(draw);
      }
    };
    const resize = () => {
      const scale = Math.min(window.devicePixelRatio || 1, 2) * 0.5;
      const width = Math.max(1, Math.round(canvas.clientWidth * scale));
      const height = Math.max(1, Math.round(canvas.clientHeight * scale));
      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width;
        canvas.height = height;
        gl.viewport(0, 0, width, height);
        gl.uniform2f(uRes, width, height);
      }
    };
    const onVisibility = () => {
      frame.visible = !document.hidden;
      resume();
    };
    const observers = [];
    if ('ResizeObserver' in window) {
      const sizer = new ResizeObserver(resize);
      sizer.observe(canvas);
      observers.push(sizer);
    }
    if ('IntersectionObserver' in window) {
      const seen = new IntersectionObserver(([entry]) => {
        frame.onScreen = entry.isIntersecting;
        resume();
      });
      seen.observe(host);
      observers.push(seen);
    }
    document.addEventListener('visibilitychange', onVisibility);
    canvas.addEventListener('webglcontextlost', (event) => {
      event.preventDefault();
      host.dataset.stage = 'static';
      unmount();
    });
    resize();
    current = { host, canvas, gl, observers, frame, onVisibility };
    host.dataset.stage = 'gl';
    resume();
  }

  window.Stage = { mount, unmount };
})();
