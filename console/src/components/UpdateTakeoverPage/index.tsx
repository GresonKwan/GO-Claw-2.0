import { type ReactNode } from "react";

/** Updates remain in the existing popover/modal; never replace the chat page. */
export function UpdateTakeoverGate({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
