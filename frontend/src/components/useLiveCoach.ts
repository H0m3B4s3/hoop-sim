import { useState } from "react";
import { api, type Summary } from "../api";

export function useLiveCoach(
  refresh: (s?: Summary) => void,
  toast: (m: string) => void,
  onFinal: (r: any) => void,
) {
  const [coach, setCoach] = useState<any | null>(null);
  const [feed, setFeed] = useState<any[]>([]);
  const [submitting, setSubmitting] = useState(false);

  // Apply a status response from the watch flow: either a pending decision or the final result.
  const handle = (r: any) => {
    if (r.summary) refresh(r.summary);
    if (r.events?.length) setFeed((prev) => [...prev, ...r.events]);
    if (r.status === "decision") setCoach(r.decision);
    else if (r.status === "final") {
      setCoach(null);
      onFinal(r);
    }
  };
  const begin = (r: any) => {
    setFeed([]);
    setCoach(null);
    handle(r);
  };
  const sendOrders = async (orders: any) => {
    setSubmitting(true);
    try {
      handle(await api.coachOrders(orders));
    } catch (e) {
      // The game may have finished elsewhere; if it's still open, Watch reopens it.
      setCoach(null);
      toast(String(e));
    } finally {
      setSubmitting(false);
    }
  };
  return { coach, feed, submitting, begin, handle, sendOrders };
}
