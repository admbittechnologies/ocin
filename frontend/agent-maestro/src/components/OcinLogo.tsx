import ocinLogo from "@/assets/ocin-logo.png";
import { cn } from "@/lib/utils";

interface OcinLogoProps {
  size?: number;
  className?: string;
}

export function OcinLogo({ size = 40, className }: OcinLogoProps) {
  return (
    <div
      className={cn("flex-shrink-0", className)}
      style={{
        width: size,
        height: size,
        backgroundColor: "hsl(var(--primary))",
        WebkitMaskImage: `url(${ocinLogo})`,
        WebkitMaskSize: "contain",
        WebkitMaskRepeat: "no-repeat",
        WebkitMaskPosition: "center",
        WebkitMaskMode: "alpha",
        maskImage: `url(${ocinLogo})`,
        maskSize: "contain",
        maskRepeat: "no-repeat",
        maskPosition: "center",
        maskMode: "alpha",
      } as React.CSSProperties}
    />
  );
}
