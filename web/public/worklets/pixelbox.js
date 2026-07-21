// PixelBox Paint Worklet — NES-style box borders with rounded pixel corners & shadows
// Extracted from pixel-ui-react (MIT) and converted to plain JS
const getInt = (props, name, fallback = 0) => {
  return parseInt(props.get(name)?.toString() || `${fallback}`, 10)
}
const getStr = (props, name, fallback = '') => {
  return props.get(name)?.toString().trim() || fallback
}

class PixelBox {
  static get inputProperties() {
    return [
      '--px-border', '--px-border-t', '--px-border-r', '--px-border-b', '--px-border-l',
      '--px-border-radius', '--px-border-radius-lt', '--px-border-radius-rt',
      '--px-border-radius-lb', '--px-border-radius-rb',
      '--px-border-color', '--px-bg-color',
      '--px-bg-shadow-border', '--px-bg-shadow-color', '--px-bg-shadow-position',
      '--px-button-group-flag', '--px-button-group-first', '--px-button-group-last',
      '--px-button-single'
    ]
  }

  paint(ctx, size, props) {
    const pbBorder = getInt(props, '--px-border') * 2
    let pbBorderRadius = getInt(props, '--px-border-radius')
    const pbBackgroundShadowBorder = getInt(props, '--px-bg-shadow-border') * 2
    const pbBackgroundShadowPosition = getStr(props, '--px-bg-shadow-position')
    const pbBorderColor = getStr(props, '--px-border-color')
    const pbBackgroundColor = getStr(props, '--px-bg-color')
    const pbBackgroundShadowColor = getStr(props, '--px-bg-shadow-color')

    const lt = getInt(props, '--px-border-radius-lt')
    const rt = getInt(props, '--px-border-radius-rt')
    const lb = getInt(props, '--px-border-radius-lb')
    const rb = getInt(props, '--px-border-radius-rb')

    const pbBorderT = getInt(props, '--px-border-t')
    const pbBorderR = getInt(props, '--px-border-r')
    const pbBorderB = getInt(props, '--px-border-b')
    const pbBorderL = getInt(props, '--px-border-l')

    const buttonGroupFlag = getInt(props, '--px-button-group-flag')
    const buttonGroupFirst = getInt(props, '--px-button-group-first')
    const buttonGroupLast = getInt(props, '--px-button-group-last')
    const buttonSingle = getInt(props, '--px-button-single')

    // Background fill removed — transparent overlay mode
    // CSS background-color shows through; worklet only draws borders & shadow lines

    // Button shadow
    if (pbBackgroundShadowBorder !== 0) {
      ctx.beginPath()
      ctx.strokeStyle = pbBackgroundShadowColor
      ctx.lineWidth = pbBackgroundShadowBorder / 2

      if (pbBorderRadius > 2 && Math.floor(size.height) <= 40) {
        switch (pbBackgroundShadowPosition) {
          case 'bottom-right':
            ctx.moveTo(0, size.height - pbBorder / 2 - pbBackgroundShadowBorder / 2 + pbBackgroundShadowBorder / 4)
            ctx.lineTo(size.width - pbBorder / 2, size.height - pbBorder / 2 - pbBackgroundShadowBorder / 2 + pbBackgroundShadowBorder / 4)
            ctx.moveTo(size.width - pbBorder - pbBackgroundShadowBorder / 2 + pbBackgroundShadowBorder / 4, pbBorder / 2)
            ctx.lineTo(size.width - pbBorder - pbBackgroundShadowBorder / 2 + pbBackgroundShadowBorder / 4, size.height - pbBorder / 2)
            break
          case 'bottom-left':
            ctx.moveTo(pbBorder / 2, size.height - pbBorder / 2 - pbBackgroundShadowBorder / 2 + pbBackgroundShadowBorder / 4)
            ctx.lineTo(size.width - pbBorder / 2, size.height - pbBorder / 2 - pbBackgroundShadowBorder / 2 + pbBackgroundShadowBorder / 4)
            ctx.moveTo((buttonGroupFirst || buttonSingle ? pbBorder : 0) + pbBackgroundShadowBorder / 2 - pbBackgroundShadowBorder / 4, pbBorder / 2)
            ctx.lineTo((buttonGroupFirst || buttonSingle ? pbBorder : 0) + pbBackgroundShadowBorder / 2 - pbBackgroundShadowBorder / 4, size.height - pbBorder / 2)
            break
          case 'top-right':
            ctx.moveTo(0, pbBorder / 2 + pbBackgroundShadowBorder / 2 - pbBackgroundShadowBorder / 4)
            ctx.lineTo(size.width - pbBorder / 2, pbBorder / 2 + pbBackgroundShadowBorder / 2 - pbBackgroundShadowBorder / 4)
            ctx.moveTo(size.width - pbBorder - pbBackgroundShadowBorder / 2 + pbBackgroundShadowBorder / 4, pbBorder / 2)
            ctx.lineTo(size.width - pbBorder - pbBackgroundShadowBorder / 2 + pbBackgroundShadowBorder / 4, size.height - pbBorder / 2)
            break
          case 'top-left':
            ctx.moveTo(0, pbBorder / 2 + pbBackgroundShadowBorder / 2 - pbBackgroundShadowBorder / 4)
            ctx.lineTo(size.width - pbBorder / 2, pbBorder / 2 + pbBackgroundShadowBorder / 2 - pbBackgroundShadowBorder / 4)
            ctx.moveTo((buttonGroupFirst || buttonSingle ? pbBorder : 0) + pbBackgroundShadowBorder / 2 - pbBackgroundShadowBorder / 4, pbBorder / 2)
            ctx.lineTo((buttonGroupFirst || buttonSingle ? pbBorder : 0) + pbBackgroundShadowBorder / 2 - pbBackgroundShadowBorder / 4, size.height - pbBorder / 2)
            break
        }
      } else {
        switch (pbBackgroundShadowPosition) {
          case 'bottom-right':
            ctx.moveTo(0, size.height - pbBorder / 2 - pbBackgroundShadowBorder / 2 + pbBackgroundShadowBorder / 4)
            ctx.lineTo(size.width - pbBorder / 2, size.height - pbBorder / 2 - pbBackgroundShadowBorder / 2 + pbBackgroundShadowBorder / 4)
            ctx.moveTo(size.width - pbBorder / 2 - pbBackgroundShadowBorder / 2 + pbBackgroundShadowBorder / 4, pbBorder / 2)
            ctx.lineTo(size.width - pbBorder / 2 - pbBackgroundShadowBorder / 2 + pbBackgroundShadowBorder / 4, size.height - pbBorder / 2)
            break
          case 'bottom-left':
            ctx.moveTo(pbBorder / 2, size.height - pbBorder / 2 - pbBackgroundShadowBorder / 2 + pbBackgroundShadowBorder / 4)
            ctx.lineTo(size.width - pbBorder / 2, size.height - pbBorder / 2 - pbBackgroundShadowBorder / 2 + pbBackgroundShadowBorder / 4)
            ctx.moveTo((buttonGroupFirst || buttonSingle ? pbBorder / 2 : 0) + pbBackgroundShadowBorder / 2 - pbBackgroundShadowBorder / 4, pbBorder / 2)
            ctx.lineTo((buttonGroupFirst || buttonSingle ? pbBorder / 2 : 0) + pbBackgroundShadowBorder / 2 - pbBackgroundShadowBorder / 4, size.height - pbBorder / 2)
            break
          case 'top-right':
            ctx.moveTo(0, pbBorder / 2 + pbBackgroundShadowBorder / 2 - pbBackgroundShadowBorder / 4)
            ctx.lineTo(size.width - pbBorder / 2, pbBorder / 2 + pbBackgroundShadowBorder / 2 - pbBackgroundShadowBorder / 4)
            ctx.moveTo(size.width - pbBorder / 2 - pbBackgroundShadowBorder / 2 + pbBackgroundShadowBorder / 4, pbBorder / 2)
            ctx.lineTo(size.width - pbBorder / 2 - pbBackgroundShadowBorder / 2 + pbBackgroundShadowBorder / 4, size.height - pbBorder / 2)
            break
          case 'top-left':
            ctx.moveTo(0, pbBorder / 2 + pbBackgroundShadowBorder / 2 - pbBackgroundShadowBorder / 4)
            ctx.lineTo(size.width - pbBorder / 2, pbBorder / 2 + pbBackgroundShadowBorder / 2 - pbBackgroundShadowBorder / 4)
            ctx.moveTo((buttonGroupFirst || buttonSingle ? pbBorder / 2 : 0) + pbBackgroundShadowBorder / 2 - pbBackgroundShadowBorder / 4, pbBorder / 2)
            ctx.lineTo((buttonGroupFirst || buttonSingle ? pbBorder / 2 : 0) + pbBackgroundShadowBorder / 2 - pbBackgroundShadowBorder / 4, size.height - pbBorder / 2)
            break
        }
      }
      ctx.stroke()
    }

    // Button rounded corners (simplified)
    if (pbBorderRadius > 0) {
      ctx.fillStyle = pbBorderColor
      if (pbBackgroundShadowBorder === 0) {
        for (let i = 1; i <= pbBorderRadius; i++) {
          if (lt) ctx.fillRect((pbBorder * (pbBorderRadius - i + 1)) / 2, (pbBorder * i) / 2, pbBorder / 2, pbBorder / 2)
          if (rt) ctx.fillRect(size.width - (pbBorder * (pbBorderRadius - i + 2)) / 2, (pbBorder * i) / 2, pbBorder / 2, pbBorder / 2)
          if (lb) ctx.fillRect((pbBorder * i) / 2, size.height - (pbBorder * (pbBorderRadius - i + 2)) / 2, pbBorder / 2, pbBorder / 2)
          if (rb) ctx.fillRect(size.width - pbBorder / 2 - (pbBorder * i) / 2, size.height - (pbBorder * (pbBorderRadius - i + 2)) / 2, pbBorder / 2, pbBorder / 2)
        }
        ctx.fill()

        // Clear areas for rounded corners
        for (let i = 0; i <= pbBorderRadius + 1; i++) {
          if (lt) ctx.clearRect(0, 0, (pbBorder * (pbBorderRadius - i + 2)) / 2, (pbBorder * i) / 2)
          if (rt) ctx.clearRect(size.width - (pbBorder * (pbBorderRadius - i + 1)) / 2, (pbBorder * i) / 2, size.width, pbBorder / 2)
          if (lb) ctx.clearRect(0, size.height - (pbBorder * (pbBorderRadius - i + 2)) / 2, (pbBorder * i) / 2, size.height - (pbBorder * (pbBorderRadius - i)) / 2)
          if (rb) ctx.clearRect(size.width - pbBorder / 2 - (pbBorder * i) / 2, size.height - (pbBorder * (pbBorderRadius - i + 1)) / 2, size.width, size.height)
        }
      }
    }

    // Button border outline
    const pbRadius = (pbBorderRadius * pbBorder) / 2
    ctx.beginPath()
    ctx.strokeStyle = pbBorderColor
    ctx.lineWidth = pbBorder

    // Up line
    if (pbBorderT) {
      if (buttonGroupFlag) {
        ctx.moveTo(pbBorderL, 0)
        ctx.lineTo(size.width - pbBorderR, 0)
      } else if (buttonGroupFirst) {
        ctx.moveTo(pbBorder / 2 + pbRadius, 0)
        ctx.lineTo(size.width - pbBorderR, 0)
      } else if (buttonGroupLast) {
        ctx.moveTo(pbBorderL, 0)
        ctx.lineTo(size.width - pbBorder / 2 - pbRadius, 0)
      } else {
        ctx.moveTo(pbBorder / 2 + pbRadius, 0)
        ctx.lineTo(size.width - pbBorder / 2 - pbRadius, 0)
      }
    }

    // Left line
    if (pbBorderL) {
      ctx.moveTo(0, pbBorder / 2 + pbRadius)
      ctx.lineTo(0, size.height - pbBorder / 2 - pbRadius)
    }

    // Bottom line
    if (pbBorderB) {
      ctx.moveTo(pbBorder / 2 + pbRadius, size.height)
      ctx.lineTo(size.width - pbBorder / 2 - pbRadius, size.height)
      if (buttonGroupFlag) {
        ctx.moveTo(pbBorderL, size.height)
        ctx.lineTo(size.width - pbBorderR, size.height)
      } else if (buttonGroupFirst) {
        ctx.moveTo(pbBorder / 2 + pbRadius, size.height)
        ctx.lineTo(size.width - pbBorderR, size.height)
      } else if (buttonGroupLast) {
        ctx.moveTo(pbBorderL, size.height)
        ctx.lineTo(size.width - pbBorder / 2 - pbRadius, size.height)
      }
    }

    // Right line
    if (pbBorderR) {
      ctx.moveTo(size.width, pbBorder / 2 + pbRadius)
      ctx.lineTo(size.width, size.height - pbBorder / 2 - pbRadius)
    }

    ctx.stroke()
    ctx.closePath()
  }
}

registerPaint('pixelbox', PixelBox)
