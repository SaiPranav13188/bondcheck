/** Renders [REDACTED_*] tokens as black bars. */
export default function RedactedText({ text }: { text: string }) {
  const parts = text.split(/(\[REDACTED_[A-Z_]+\])/g);
  return (
    <>
      {parts.map((p, i) => p.startsWith("[REDACTED_")
        ? <span key={i} className="redaction" title={p.replace(/[[\]]/g, "").replace("_", " ").toLowerCase()}>████</span>
        : <span key={i}>{p}</span>)}
    </>
  );
}
