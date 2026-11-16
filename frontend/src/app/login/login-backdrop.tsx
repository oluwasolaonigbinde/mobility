// Decorative background for the sign-in page: a street map with vehicles
// driving along it, over soft green corners. Nothing here is interactive.

const ROADS = [
  { id: "road-a", d: "M-60 650 C240 580 420 500 650 470 S1040 330 1260 100", width: 9 },
  { id: "road-b", d: "M180 -60 C240 190 300 440 275 860", width: 6 },
  { id: "road-c", d: "M-60 230 L400 255 C620 265 840 460 1260 495", width: 6 },
  { id: "road-d", d: "M970 -60 C940 210 1040 480 1015 860", width: 5 },
  { id: "road-e", d: "M-60 500 L275 515 L650 470 L715 860", width: 3 },
];

const STREETS =
  "M780 -40 L830 450 M400 255 L370 -40 M1015 495 L1240 650 M715 650 L1015 680 " +
  "M-40 80 L1240 40 M-40 790 L1240 765";

const TRACE = "M1130 170 C1000 265 910 230 845 345 S700 590 485 590 S195 665 65 760";

type Vehicle = "car" | "bus" | "keke" | "okada";

// [road, vehicle, seconds per trip, drives the road backwards, starting point 0..1]
const FLEET: [string, Vehicle, number, boolean, number][] = [
  ["road-a", "car", 14, false, 0],
  ["road-a", "bus", 22, true, 0.4],
  ["road-b", "okada", 8, false, 0.2],
  ["road-c", "keke", 16, true, 0],
  ["road-c", "car", 12, false, 0.55],
  ["road-d", "car", 11, false, 0.3],
  ["road-d", "okada", 9, true, 0.7],
  ["road-e", "keke", 13, false, 0.5],
];

// Top-down icons facing +x, so rotate="auto" steers them along the road.
function VehicleIcon({ kind }: { kind: Vehicle }) {
  switch (kind) {
    case "car":
      return (
        <g>
          <rect x={-9} y={-4.5} width={18} height={9} rx={3} fill="#256f1a" />
          <rect x={1} y={-3.5} width={4} height={7} rx={1} fill="#c8f6d0" />
          <rect x={-6} y={-3.5} width={3} height={7} rx={1} fill="#c8f6d0" opacity={0.7} />
        </g>
      );
    case "bus":
      return (
        <g>
          <rect x={-15} y={-5} width={30} height={10} rx={2} fill="#0e3a0a" />
          <rect x={10} y={-4} width={3} height={8} rx={1} fill="#c8f6d0" />
          <path d="M-11 -5 V5 M-5 -5 V5 M1 -5 V5" stroke="#f2c94c" strokeWidth={1} />
        </g>
      );
    case "keke":
      return (
        <g>
          <path d="M-7 -5 H3 L8 0 L3 5 H-7 Z" fill="#d9a520" />
          <rect x={-5} y={-3.5} width={6} height={7} rx={1} fill="#0e3a0a" opacity={0.35} />
        </g>
      );
    case "okada":
      return (
        <g>
          <rect x={-6} y={-1.5} width={12} height={3} rx={1.5} fill="#0e3a0a" />
          <circle r={2.6} fill="#256f1a" />
          <path d="M4 -3.5 V3.5" stroke="#0e3a0a" strokeWidth={1.4} strokeLinecap="round" />
        </g>
      );
  }
}

export function LoginBackdrop() {
  return (
    <div className="pointer-events-none absolute inset-0" aria-hidden>
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_0%_100%,rgb(37_111_26/0.33),transparent_45%),radial-gradient(circle_at_100%_0%,rgb(37_111_26/0.25),transparent_40%),radial-gradient(circle_at_95%_95%,rgb(242_201_76/0.2),transparent_30%)]" />
      <svg
        className="absolute inset-0 h-full w-full [mask-image:radial-gradient(ellipse_at_center,transparent_18%,black_58%)]"
        viewBox="0 0 1200 800"
        preserveAspectRatio="xMidYMid slice"
        focusable="false"
      >
        <g fill="none" stroke="rgb(37 111 26 / 0.2)" strokeLinecap="round" strokeLinejoin="round">
          <path d={STREETS} strokeWidth={2.5} stroke="rgb(37 111 26 / 0.12)" />
          {ROADS.map((road) => (
            <path key={road.id} id={road.id} d={road.d} strokeWidth={road.width} />
          ))}
          <circle cx={650} cy={470} r={48} strokeWidth={4} />
        </g>
        <g fill="none" stroke="#256f1a" strokeOpacity={0.6} strokeWidth={2} strokeDasharray="5 7">
          <path d={TRACE} className="motion-safe:hidden" />
          <path d={TRACE} className="motion-reduce:hidden">
            <animate
              attributeName="stroke-dashoffset"
              from="0"
              to="-24"
              dur="1.4s"
              repeatCount="indefinite"
            />
          </path>
        </g>
        <g className="motion-reduce:hidden">
          {FLEET.map(([road, kind, seconds, reverse, start]) => (
            <g key={`${road}-${kind}`}>
              <animateMotion
                dur={`${seconds}s`}
                begin={`-${(start * seconds).toFixed(1)}s`}
                repeatCount="indefinite"
                keyPoints={reverse ? "1;0" : "0;1"}
                keyTimes="0;1"
                calcMode="linear"
                rotate="auto"
              >
                <mpath href={`#${road}`} />
              </animateMotion>
              <g transform="scale(1.6)">
                <VehicleIcon kind={kind} />
              </g>
            </g>
          ))}
        </g>
      </svg>
    </div>
  );
}
