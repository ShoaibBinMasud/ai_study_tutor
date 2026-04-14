import type { LearningPathPlan, LearningPathSource } from '../types';

export function sourceProgress(src: LearningPathSource) {
  const total = src.units.length;
  const done  = src.units.filter(u => u.completed).length;
  return { total, done, pct: total === 0 ? 0 : Math.round((done / total) * 100) };
}

export function overallProgress(plan: LearningPathPlan) {
  const total = plan.sources.reduce((a, s) => a + s.units.length, 0);
  const done  = plan.sources.reduce((a, s) => a + s.units.filter(u => u.completed).length, 0);
  return { total, done, pct: total === 0 ? 0 : Math.round((done / total) * 100) };
}
