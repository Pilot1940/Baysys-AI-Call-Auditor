/** Single call deep-dive — scaffold only. Full build is Prompt B. */

import { useParams } from "react-router-dom";

export default function CallDetailPage() {
  const { id } = useParams();
  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">
        Call Detail — #{id}
      </h1>
      <p className="text-gray-600">Call detail scaffold. Full build in Prompt B.</p>
    </div>
  );
}
