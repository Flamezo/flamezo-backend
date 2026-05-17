import { useCallback } from 'react';

interface PrintOptions {
  type: 'RECEIPT' | 'KOT';
  restaurant?: any;
}

export function usePrint() {
  const generateReceiptHTML = (order: any, restaurant: any) => {
    const date = new Date(order.creation || Date.now()).toLocaleString();
    const items = order.order_items || [];
    const currencySymbol = '₹'; // Default to INR based on earlier context

    const itemsHTML = items.map((item: any) => `
      <tr>
        <td style="padding: 4px 0; vertical-align: top;">
          <div style="font-weight: bold;">${item.product_name || item.product}</div>
          ${item.customizations ? `<div style="font-size: 10px; color: #666; font-style: italic;">${renderCustomizations(item.customizations)}</div>` : ''}
        </td>
        <td style="padding: 4px 0; text-align: center; vertical-align: top;">${item.quantity}</td>
        <td style="padding: 4px 0; text-align: right; vertical-align: top;">${currencySymbol}${((item.unit_price || 0)).toFixed(2)}</td>
        <td style="padding: 4px 0; text-align: right; vertical-align: top;">${currencySymbol}${((item.total_price || item.unit_price * item.quantity || 0)).toFixed(2)}</td>
      </tr>
    `).join('');

    return `
      <!DOCTYPE html>
      <html>
      <head>
        <style>
          @page { size: auto; margin: 0mm; }
          body { 
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            font-size: 12px; 
            line-height: 1.4; 
            color: #000;
            margin: 0;
            padding: 20px;
            width: 80mm; /* Standard thermal printer width */
          }
          .header { text-align: center; margin-bottom: 15px; border-bottom: 1px dashed #ccc; padding-bottom: 15px; }
          .restaurant-name { font-size: 18px; font-weight: 900; text-transform: uppercase; margin: 0 0 5px 0; }
          .restaurant-info { font-size: 10px; color: #444; margin: 2px 0; }
          .order-info { margin-bottom: 15px; font-size: 11px; }
          .order-info div { display: flex; justify-content: space-between; margin-bottom: 2px; }
          .table { width: 100%; border-collapse: collapse; margin-bottom: 15px; }
          .table th { border-bottom: 1px solid #000; text-align: left; padding: 5px 0; font-size: 10px; text-transform: uppercase; }
          .totals { border-top: 1px solid #000; padding-top: 8px; }
          .total-row { display: flex; justify-content: space-between; margin-bottom: 3px; font-weight: 500; }
          .total-row.grand-total { font-size: 16px; font-weight: 900; margin-top: 8px; border-top: 1px dashed #ccc; padding-top: 8px; }
          .footer { text-align: center; margin-top: 25px; font-size: 10px; color: #666; border-top: 1px dashed #ccc; padding-top: 15px; }
          .tag { display: inline-block; padding: 2px 6px; background: #000; color: #fff; font-size: 9px; font-weight: 900; border-radius: 3px; text-transform: uppercase; }
        </style>
      </head>
      <body>
        <div class="header">
          <h1 class="restaurant-name">${restaurant?.restaurant_name || 'FLAMEZO RESTAURANT'}</h1>
          <p class="restaurant-info">${restaurant?.address || 'Restaurant Address'}</p>
          <p class="restaurant-info">PH: ${restaurant?.contact_phone || 'N/A'}</p>
        </div>

        <div class="order-info">
          <div><span>Order ID:</span> <strong>#${order.order_number || order.name.split('-').pop()}</strong></div>
          <div><span>Date:</span> <span>${date}</span></div>
          <div><span>Type:</span> <span class="tag">${(order.order_type || 'dine_in').replace('_', ' ')}</span></div>
          ${order.table_number ? `<div><span>Table:</span> <strong>Table ${order.table_number}</strong></div>` : ''}
          <div><span>Customer:</span> <span>${order.customer_name || 'Guest'}</span></div>
        </div>

        <table class="table">
          <thead>
            <tr>
              <th style="width: 50%;">Item</th>
              <th style="text-align: center;">Qty</th>
              <th style="text-align: right;">Rate</th>
              <th style="text-align: right;">Amt</th>
            </tr>
          </thead>
          <tbody>
            ${itemsHTML}
          </tbody>
        </table>

        <div class="totals">
          <div class="total-row">
            <span>Subtotal</span>
            <span>${currencySymbol}${order.subtotal?.toFixed(2) || '0.00'}</span>
          </div>
          ${order.discount ? `
            <div class="total-row" style="color: #000;">
              <span>Discount</span>
              <span>-${currencySymbol}${order.discount.toFixed(2)}</span>
            </div>
          ` : ''}
          ${order.tax ? `
            <div class="total-row">
              <span>GST (Incl.)</span>
              <span>${currencySymbol}${order.tax.toFixed(2)}</span>
            </div>
          ` : ''}
          <div class="total-row grand-total">
            <span>GRAND TOTAL</span>
            <span>${currencySymbol}${order.total?.toFixed(2) || '0.00'}</span>
          </div>
        </div>

        <div class="footer">
          <p>Thank you for dining with us!</p>
          <p style="font-weight: bold; margin-top: 5px;">Powered by Flamezo</p>
        </div>
      </body>
      </html>
    `;
  };

  const generateKOTHTML = (order: any) => {
    const date = new Date().toLocaleString();
    const items = order.order_items || [];

    const itemsHTML = items.map((item: any) => `
      <tr>
        <td style="padding: 8px 0; border-bottom: 1px solid #eee; width: 30px; font-size: 20px; font-weight: 900;">${item.quantity}</td>
        <td style="padding: 8px 0; border-bottom: 1px solid #eee;">
          <div style="font-size: 16px; font-weight: 800;">${item.product_name || item.product}</div>
          ${item.customizations ? `<div style="font-size: 12px; font-weight: 600; color: #333; margin-top: 4px; padding: 4px; background: #f9f9f9; border-radius: 4px;">${renderCustomizations(item.customizations)}</div>` : ''}
        </td>
      </tr>
    `).join('');

    return `
      <!DOCTYPE html>
      <html>
      <head>
        <style>
          @page { size: auto; margin: 0mm; }
          body { 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            font-size: 14px; 
            line-height: 1.2; 
            color: #000;
            margin: 0;
            padding: 15px;
            width: 80mm;
          }
          .kot-header { text-align: center; border-bottom: 3px solid #000; padding-bottom: 10px; margin-bottom: 15px; }
          .kot-title { font-size: 24px; font-weight: 900; margin: 0; text-transform: uppercase; letter-spacing: 2px; }
          .order-details { margin-bottom: 15px; font-size: 14px; font-weight: 700; }
          .order-details div { display: flex; justify-content: space-between; margin-bottom: 4px; }
          .table { width: 100%; border-collapse: collapse; }
          .table th { text-align: left; padding: 5px 0; border-bottom: 2px solid #000; font-size: 12px; }
          .footer { text-align: center; margin-top: 20px; border-top: 2px solid #000; padding-top: 10px; font-size: 11px; font-weight: 800; }
          .big-text { font-size: 22px; font-weight: 900; }
        </style>
      </head>
      <body>
        <div class="kot-header">
          <h1 class="kot-title">KITCHEN ORDER</h1>
          <div style="margin-top: 5px; font-size: 12px;">${date}</div>
        </div>

        <div class="order-details">
          <div><span>ORDER ID:</span> <span>#${order.order_number || order.name.split('-').pop()}</span></div>
          <div><span>TYPE:</span> <span style="background: #000; color: #fff; padding: 0 4px;">${(order.order_type || 'dine_in').toUpperCase()}</span></div>
          ${order.table_number !== undefined ? `<div class="big-text"><span>TABLE:</span> <span>${order.table_number}</span></div>` : ''}
        </div>

        <table class="table">
          <thead>
            <tr>
              <th style="text-align: left;">QTY</th>
              <th style="text-align: left;">ITEM & CUSTOMIZATIONS</th>
            </tr>
          </thead>
          <tbody>
            ${itemsHTML}
          </tbody>
        </table>

        ${order.cooking_instructions ? `
          <div style="margin-top: 15px; padding: 10px; border: 2px solid #000; border-radius: 8px;">
            <div style="font-size: 12px; font-weight: 900; text-transform: uppercase; margin-bottom: 4px;">Special Instructions:</div>
            <div style="font-size: 14px; font-weight: 700; font-style: italic;">${order.cooking_instructions}</div>
          </div>
        ` : ''}

        <div class="footer">
          END OF KOT
        </div>
      </body>
      </html>
    `;
  };

  const renderCustomizations = (customizations: any) => {
    if (!customizations) return '';
    try {
      const parsed = typeof customizations === 'string' ? JSON.parse(customizations) : customizations;
      return Object.entries(parsed)
        .map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join(', ') : value}`)
        .join(' | ');
    } catch {
      return '';
    }
  };

  const print = useCallback((html: string) => {
    const iframe = document.createElement('iframe');
    iframe.style.display = 'none';
    document.body.appendChild(iframe);

    const doc = iframe.contentWindow?.document || iframe.contentDocument;
    if (!doc) return;

    doc.open();
    doc.write(html);
    doc.close();

    // Wait for images/styles to load before printing
    iframe.contentWindow?.focus();
    setTimeout(() => {
      iframe.contentWindow?.print();
      // Remove the iframe after printing is initiated
      setTimeout(() => {
        document.body.removeChild(iframe);
      }, 1000);
    }, 500);
  }, []);

  const handlePrint = useCallback((order: any, options: PrintOptions) => {
    if (options.type === 'RECEIPT') {
      const html = generateReceiptHTML(order, options.restaurant);
      print(html);
    } else {
      const html = generateKOTHTML(order);
      print(html);
    }
  }, [print]);

  return { print: handlePrint };
}
