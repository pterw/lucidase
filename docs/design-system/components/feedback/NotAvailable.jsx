import React from "react";
export function NotAvailable({ reason, children = "Not available" }) {
  return <span title={reason} style={{ color: "var(--text-subtle)", fontStyle: "italic", fontFamily: "var(--font-sans)", fontWeight: 400 }}>{children}</span>;
}
