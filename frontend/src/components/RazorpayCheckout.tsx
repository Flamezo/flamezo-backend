import React, { useEffect, useState } from 'react';
import { useFrappePostCall } from '@/lib/frappe';
import { Button } from './ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Loader2, CreditCard, CheckCircle, XCircle } from 'lucide-react';
import { toast } from 'sonner';
import { getFrappeError } from '@/lib/utils';

// Extend window object to include Razorpay
declare global {
  interface Window {
    Razorpay: any;
  }
}

interface OrderItem {
  product_id: string;
  product_name: string;
  quantity: number;
  rate: number;
  amount: number;
}

interface RazorpayCheckoutProps {
  restaurantId: string;
  orderItems: OrderItem[];
  totalAmount: number;
  customerName?: string;
  customerEmail?: string;
  customerPhone?: string;
  tableNumber?: number;
  onSuccess?: (orderId: string, paymentId: string) => void;
  onFailure?: (error: any) => void;
}

interface PaymentOrderResponse {
  success: boolean;
  data?: {
    razorpay_order_id: string;
    amount: number;
    currency: string;
    key_id: string;
    order_id: string;
    platform_fee: number;
    restaurant_amount: number;
  };
  error?: string;
}

const RazorpayCheckout: React.FC<RazorpayCheckoutProps> = ({
  restaurantId,
  orderItems,
  totalAmount,
  customerName,
  customerEmail,
  customerPhone,
  tableNumber,
  onSuccess,
  onFailure
}) => {
  const [isLoading, setIsLoading] = useState(false);
  const [paymentStatus, setPaymentStatus] = useState<'idle' | 'processing' | 'success' | 'failed'>('idle');
  const [razorpayLoaded, setRazorpayLoaded] = useState(false);

  // API calls
  const { call: createPaymentOrder } = useFrappePostCall<PaymentOrderResponse>(
    'flamezo_backend.flamezo.api.payments.create_payment_order'
  );

  const { call: verifyPayment } = useFrappePostCall(
    'flamezo_backend.flamezo.api.payments.verify_payment'
  );

  // Load Razorpay script
  useEffect(() => {
    const loadRazorpayScript = () => {
      return new Promise((resolve) => {
        if (window.Razorpay) {
          setRazorpayLoaded(true);
          resolve(true);
          return;
        }

        const script = document.createElement('script');
        script.src = 'https://checkout.razorpay.com/v1/checkout.js';
        script.onload = () => {
          setRazorpayLoaded(true);
          resolve(true);
        };
        script.onerror = () => {
          console.error('Failed to load Razorpay script');
          resolve(false);
        };
        document.body.appendChild(script);
      });
    };

    loadRazorpayScript();
  }, []);

  const handlePayment = async () => {
    if (!razorpayLoaded) {
      toast.error('Payment system is loading. Please try again.');
      return;
    }

    setIsLoading(true);
    setPaymentStatus('processing');

    try {
      // Create payment order
      const response = await createPaymentOrder({
        restaurant_id: restaurantId,
        order_items: JSON.stringify(orderItems),
        total_amount: totalAmount,
        customer_name: customerName,
        customer_email: customerEmail,
        customer_phone: customerPhone,
        table_number: tableNumber
      });

      if (!response?.success || !response.data) {
        throw new Error(response?.error || 'Failed to create payment order');
      }

      const { razorpay_order_id, amount, key_id, order_id, platform_fee, restaurant_amount } = response.data;

      // Initialize Razorpay checkout
      const options = {
        key: key_id,
        amount: amount,
        currency: 'INR',
        name: 'Flamezo',
        description: `Order payment for ${restaurantId}`,
        order_id: razorpay_order_id,
        prefill: {
          name: customerName || '',
          email: customerEmail || '',
          contact: customerPhone || ''
        },
        theme: {
          color: '#3B82F6'
        },
        handler: async (paymentResponse: any) => {
          try {
            // Verify payment on backend
            await verifyPayment({
              razorpay_order_id: razorpay_order_id,
              razorpay_payment_id: paymentResponse.razorpay_payment_id,
              razorpay_signature: paymentResponse.razorpay_signature
            });

            setPaymentStatus('success');
            toast.success('Payment successful!');
            
            if (onSuccess) {
              onSuccess(order_id, paymentResponse.razorpay_payment_id);
            }
          } catch (error: any) {
            console.error('Payment verification failed:', error);
            setPaymentStatus('failed');
            toast.error('Payment verification failed', { description: getFrappeError(error) });
            
            if (onFailure) {
              onFailure(error);
            }
          }
        },
        modal: {
          ondismiss: () => {
            setPaymentStatus('idle');
            setIsLoading(false);
            toast.info('Payment cancelled');
          }
        }
      };

      const rzp = new window.Razorpay(options);
      
      rzp.on('payment.failed', (response: any) => {
        setPaymentStatus('failed');
        setIsLoading(false);
        toast.error('Payment failed', { description: response.error?.description || 'Unknown error' });
        
        if (onFailure) {
          onFailure(response.error);
        }
      });

      rzp.open();
      setIsLoading(false);

    } catch (error: any) {
      console.error('Payment initiation failed:', error);
      setPaymentStatus('failed');
      setIsLoading(false);
      toast.error('Failed to initiate payment', { description: getFrappeError(error) });
      
      if (onFailure) {
        onFailure(error);
      }
    }
  };

  const getStatusIcon = () => {
    switch (paymentStatus) {
      case 'processing':
        return <Loader2 className="h-5 w-5 animate-spin" />;
      case 'success':
        return <CheckCircle className="h-5 w-5 text-green-500" />;
      case 'failed':
        return <XCircle className="h-5 w-5 text-red-500" />;
      default:
        return <CreditCard className="h-5 w-5" />;
    }
  };

  const getStatusText = () => {
    switch (paymentStatus) {
      case 'processing':
        return 'Processing payment...';
      case 'success':
        return 'Payment successful!';
      case 'failed':
        return 'Payment failed';
      default:
        return 'Pay with Razorpay';
    }
  };

  return (
    <Card className="w-full max-w-md mx-auto">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          {getStatusIcon()}
          Payment Details
        </CardTitle>
        <CardDescription>
          Complete your order payment securely
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Order Summary */}
        <div className="space-y-2">
          <h4 className="font-medium">Order Summary</h4>
          <div className="text-sm text-gray-600 space-y-1">
            {orderItems.map((item, index) => (
              <div key={index} className="flex justify-between">
                <span>{item.product_name} x {item.quantity}</span>
                <span>₹{item.amount.toFixed(2)}</span>
              </div>
            ))}
            <div className="border-t pt-1 font-medium flex justify-between">
              <span>Total Amount</span>
              <span>₹{totalAmount.toFixed(2)}</span>
            </div>
          </div>
        </div>

        {/* Customer Details */}
        {(customerName || customerEmail || customerPhone) && (
          <div className="space-y-2">
            <h4 className="font-medium">Customer Details</h4>
            <div className="text-sm text-gray-600 space-y-1">
              {customerName && <div>Name: {customerName}</div>}
              {customerEmail && <div>Email: {customerEmail}</div>}
              {customerPhone && <div>Phone: {customerPhone}</div>}
              {tableNumber && <div>Table: {tableNumber}</div>}
            </div>
          </div>
        )}

        {/* Payment Button */}
        <Button
          onClick={handlePayment}
          disabled={isLoading || !razorpayLoaded || paymentStatus === 'success'}
          className="w-full"
          size="lg"
        >
          {isLoading ? (
            <Loader2 className="h-4 w-4 animate-spin mr-2" />
          ) : (
            getStatusIcon()
          )}
          <span className="ml-2">{getStatusText()}</span>
        </Button>

        {/* Status Messages */}
        {paymentStatus === 'success' && (
          <div className="text-center text-sm text-green-600 bg-green-50 p-2 rounded">
            Your payment has been processed successfully!
          </div>
        )}

        {paymentStatus === 'failed' && (
          <div className="text-center text-sm text-red-600 bg-red-50 p-2 rounded">
            Payment failed. Please try again or contact support.
          </div>
        )}

        {!razorpayLoaded && (
          <div className="text-center text-sm text-gray-500">
            Loading payment system...
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default RazorpayCheckout;