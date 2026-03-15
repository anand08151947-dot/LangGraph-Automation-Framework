
import React from 'react';

/** FE-UX-3: Reusable loading skeleton that matches content shape. */
export const Skeleton: React.FC<{ className?: string }> = ({ className = '' }) => (
  <div className={`animate-pulse bg-slate-200 rounded-lg ${className}`} />
);

/** Skeleton for a single run list item */
export const RunItemSkeleton: React.FC = () => (
  <div className="w-full p-4 rounded-xl border border-slate-100 bg-white space-y-2">
    <div className="flex justify-between items-start">
      <Skeleton className="h-4 w-1/2" />
      <Skeleton className="h-5 w-16 rounded-full" />
    </div>
    <div className="flex justify-between">
      <Skeleton className="h-3 w-1/3" />
      <Skeleton className="h-3 w-1/4" />
    </div>
  </div>
);

/** Skeleton for a table row */
export const TableRowSkeleton: React.FC<{ cols?: number }> = ({ cols = 4 }) => (
  <tr>
    {Array.from({ length: cols }).map((_, i) => (
      <td key={i} className="py-4 pr-4">
        <Skeleton className="h-4 w-full" />
      </td>
    ))}
  </tr>
);

/** Skeleton for a stats card */
export const StatCardSkeleton: React.FC = () => (
  <div className="p-6 rounded-2xl border border-slate-100 bg-white space-y-3">
    <div className="flex items-center gap-4">
      <Skeleton className="w-12 h-12 rounded-xl" />
      <div className="space-y-2 flex-1">
        <Skeleton className="h-3 w-1/2" />
        <Skeleton className="h-6 w-1/3" />
      </div>
    </div>
  </div>
);
