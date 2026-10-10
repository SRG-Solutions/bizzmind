import { notFound } from "next/navigation";
import RecordingFlow from "./recording-flow";

// Local recording fixture only. No AI calls, uploads or project mutations.
export default function RecordingPage() {
  if (process.env.NODE_ENV !== "development") notFound();
  return <RecordingFlow />;
}
