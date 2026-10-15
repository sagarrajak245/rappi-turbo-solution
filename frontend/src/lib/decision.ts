/**
 * React key for the decision form. A re-plan brings a new proposal, so the form remounts and
 * drops the qty and reason typed for the old one; within one proposal the input is kept.
 */
export function decisionFormKey(run: { id: string; replans_done: number }): string {
  return `${run.id}:${run.replans_done}`;
}
