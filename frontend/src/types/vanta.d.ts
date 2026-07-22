// Vanta ships no type definitions. Each effect module default-exports a factory
// that takes an options object and returns a handle with destroy()/setOptions().
declare module "vanta/dist/vanta.fog.min" {
  const effect: (options: Record<string, unknown>) => {
    destroy: () => void;
    setOptions: (options: Record<string, unknown>) => void;
    resize: () => void;
  };
  export default effect;
}

declare module "vanta/dist/vanta.topology.min" {
  const effect: (options: Record<string, unknown>) => {
    destroy: () => void;
    setOptions: (options: Record<string, unknown>) => void;
    resize: () => void;
  };
  export default effect;
}

declare module "vanta/dist/vanta.waves.min" {
  const effect: (options: Record<string, unknown>) => {
    destroy: () => void;
    setOptions: (options: Record<string, unknown>) => void;
    resize: () => void;
  };
  export default effect;
}
