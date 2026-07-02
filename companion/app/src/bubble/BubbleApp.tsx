import { Bubble } from "@/components/Bubble";

export function BubbleApp() {
  return (
    <div
      style={{
        width: "100vw",
        height: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "transparent",
      }}
    >
      <Bubble />
    </div>
  );
}
