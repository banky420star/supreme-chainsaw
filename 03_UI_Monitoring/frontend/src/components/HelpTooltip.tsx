/**
 * HelpTooltip Component
 *
 * Provides contextual help and explanations for UI elements.
 * Shows an info icon that displays explanatory text on hover.
 */
import React, { useState } from 'react'

interface HelpTooltipProps {
  /** The help text to display */
  text: string
  /** Optional title for the tooltip */
  title?: string
  /** Size of the icon */
  size?: 'sm' | 'md' | 'lg'
  /** Position of the tooltip relative to the icon */
  position?: 'top' | 'bottom' | 'left' | 'right'
}

const sizeMap = {
  sm: { icon: 14, maxWidth: 240 },
  md: { icon: 16, maxWidth: 280 },
  lg: { icon: 20, maxWidth: 320 },
}

export const HelpTooltip: React.FC<HelpTooltipProps> = ({
  text,
  title,
  size = 'md',
  position = 'top',
}) => {
  const [isVisible, setIsVisible] = useState(false)
  const { icon, maxWidth } = sizeMap[size]

  const positionStyles: Record<string, React.CSSProperties> = {
    top: { bottom: '100%', left: '50%', transform: 'translateX(-50%)', marginBottom: 8 },
    bottom: { top: '100%', left: '50%', transform: 'translateX(-50%)', marginTop: 8 },
    left: { right: '100%', top: '50%', transform: 'translateY(-50%)', marginRight: 8 },
    right: { left: '100%', top: '50%', transform: 'translateY(-50%)', marginLeft: 8 },
  }

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        position: 'relative',
        cursor: 'help',
      }}
      onMouseEnter={() => setIsVisible(true)}
      onMouseLeave={() => setIsVisible(false)}
    >
      {/* Info Icon */}
      <svg
        width={icon}
        height={icon}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        style={{
          color: isVisible ? '#5ad7ff' : '#7a94b0',
          transition: 'color 0.2s',
        }}
      >
        <circle cx="12" cy="12" r="10" />
        <line x1="12" y1="16" x2="12" y2="12" />
        <line x1="12" y1="8" x2="12.01" y2="8" />
      </svg>

      {/* Tooltip */}
      {isVisible && (
        <div
          style={{
            position: 'absolute',
            ...positionStyles[position],
            background: 'rgba(13, 23, 38, 0.98)',
            border: '1px solid rgba(90, 215, 255, 0.3)',
            borderRadius: 8,
            padding: '12px 14px',
            maxWidth,
            zIndex: 1000,
            boxShadow: '0 4px 20px rgba(0, 0, 0, 0.4)',
            fontSize: 12,
            lineHeight: 1.5,
            color: '#e8f4ff',
          }}
        >
          {title && (
            <div
              style={{
                fontWeight: 600,
                color: '#5ad7ff',
                marginBottom: 6,
                fontSize: 13,
              }}
            >
              {title}
            </div>
          )}
          <div style={{ color: '#97a9c6' }}>{text}</div>
        </div>
      )}
    </span>
  )
}

export default HelpTooltip
