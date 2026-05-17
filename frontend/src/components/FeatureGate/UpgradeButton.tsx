/**
 * UpgradeButton Component
 * 
 * CTA button for upgrading to GOLD plan
 */

import { ArrowUpRight } from 'lucide-react';

interface UpgradeButtonProps {
  size?: 'sm' | 'md' | 'lg';
  variant?: 'primary' | 'secondary';
  className?: string;
}

export function UpgradeButton({ size = 'md', variant = 'primary', className = '' }: UpgradeButtonProps) {
  const sizeClasses = {
    sm: 'px-3 py-1.5 text-sm',
    md: 'px-6 py-2 text-base',
    lg: 'px-8 py-3 text-lg',
  };

  const variantClasses = {
    primary: 'bg-gradient-to-r from-orange-500 to-red-500 hover:from-orange-600 hover:to-red-600 text-white',
    secondary: 'bg-white border-2 border-orange-500 text-orange-600 hover:bg-orange-50',
  };

  return (
    <button
      onClick={() => {
        window.location.href = '/flamezo_backend/autopay-setup';
      }}
      className={`
        inline-flex items-center gap-2 font-semibold rounded-lg transition-all
        ${sizeClasses[size]}
        ${variantClasses[variant]}
        ${className}
      `}
    >
      Upgrade to GOLD
      <ArrowUpRight className="w-4 h-4" />
    </button>
  );
}
