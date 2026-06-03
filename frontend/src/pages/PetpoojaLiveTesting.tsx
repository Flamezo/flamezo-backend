import { useState, useRef } from 'react'
import { useRestaurant } from '../contexts/RestaurantContext'
import { Button } from '../components/ui/button'
import { Badge } from '../components/ui/badge'
import { Input } from '../components/ui/input'
import {
  CheckCircle2, XCircle, Loader2, Play, RefreshCw,
  Wifi, ShoppingCart, ToggleLeft, Store, Truck, Clock,
  ChevronDown, Copy, Terminal
} from 'lucide-react'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'


// ─── Config ─────────────────────────────────────────────────────────────────

const SAVE_ORDER_URL = 'https://qle1yy2ydc.execute-api.ap-southeast-1.amazonaws.com/V1/save_order'
const CALLBACK_URL = 'https://backend.flamezo.in/api/method/flamezo_backend.flamezo.api.pos.pos_gateway'
const CREDS = {
  app_key: 'yk5aniupvtjgwr1839fxzds70hoe2cm6',
  app_secret: '3c88718f646c5a808828c9f27b8775b7129323e7',
  access_token: 'b4bfad4f5c1c9568e4e76efe4f4e00c9a130cdbc',
}
const REST_ID = 'ghvua4js'


// ─── Types ──────────────────────────────────────────────────────────────────

type TestStatus = 'idle' | 'running' | 'pass' | 'fail'

interface TestResult {
  status: TestStatus
  response?: string
  time?: number
  error?: string
}

interface LogEntry {
  time: string
  type: 'info' | 'success' | 'error' | 'request' | 'response'
  message: string
}


// ─── Status Icon ────────────────────────────────────────────────────────

function StatusIcon({ status }: { status: TestStatus }) {
  if (status === 'running') return <Loader2 className="w-4 h-4 animate-spin text-blue-500" />
  if (status === 'pass') return <CheckCircle2 className="w-4 h-4 text-green-500" />
  if (status === 'fail') return <XCircle className="w-4 h-4 text-red-500" />
  return <div className="w-4 h-4 rounded-full border-2 border-muted-foreground/30" />
}


// ─── Test Card Component ────────────────────────────────────────────────────

function TestCard({ icon, title, description, result, onRun, note }: {
  icon: React.ReactNode
  title: string
  description: string
  result?: TestResult
  onRun: () => void
  note?: string
}) {
  const status = result?.status || 'idle'
  return (
    <div className={cn("border rounded-lg p-3 transition-all", {
      'border-green-200 bg-green-500/5': status === 'pass',
      'border-red-200 bg-red-500/5': status === 'fail',
      'border-blue-200 bg-blue-500/5': status === 'running',
    })}>
      <div className="flex items-center gap-3">
        <div className="text-primary">{icon}</div>
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-bold">{title}</h3>
          <p className="text-[10px] text-muted-foreground">{description}</p>
        </div>
        <StatusIcon status={status} />
        <Button variant="outline" size="sm" className="h-7 text-xs" onClick={onRun}
          disabled={status === 'running'}>
          {status === 'running' ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
        </Button>
      </div>
      {result?.time && <p className="text-[10px] text-muted-foreground mt-1 ml-7">{result.time}ms</p>}
      {result?.error && <p className="text-[10px] text-red-500 mt-1 ml-7">{result.error}</p>}
      {note && <p className="text-[10px] text-muted-foreground/60 mt-1 ml-7 italic">{note}</p>}
    </div>
  )
}


// ─── Page ───────────────────────────────────────────────────────────────────

export default function PetpoojaLiveTesting() {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [results, setResults] = useState<Record<string, TestResult>>({})
  const [orderIds, setOrderIds] = useState<string[]>([])
  const logsEndRef = useRef<HTMLDivElement>(null)

  const addLog = (type: LogEntry['type'], message: string) => {
    const entry: LogEntry = { time: new Date().toLocaleTimeString(), type, message }
    setLogs(prev => [...prev, entry])
    setTimeout(() => logsEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 100)
  }

  const setTest = (name: string, result: TestResult) => {
    setResults(prev => ({ ...prev, [name]: result }))
  }

  const now = () => {
    const d = new Date()
    return {
      date: d.toISOString().split('T')[0],
      time: d.toTimeString().split(' ')[0],
      full: d.toISOString().replace('T', ' ').split('.')[0],
    }
  }

  // ─── Test: Endpoint Health ──────────────────────────────────────────────

  const testEndpointHealth = async () => {
    setTest('health', { status: 'running' })
    addLog('request', `POST ${CALLBACK_URL}`)
    const start = Date.now()
    try {
      const r = await fetch(CALLBACK_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ test: true }),
      })
      const data = await r.json()
      const ms = Date.now() - start
      addLog('response', `${r.status} (${ms}ms) — ${JSON.stringify(data).slice(0, 200)}`)
      if (r.ok) {
        setTest('health', { status: 'pass', response: JSON.stringify(data), time: ms })
        addLog('success', 'Callback endpoint is reachable and responding')
      } else {
        setTest('health', { status: 'fail', error: `HTTP ${r.status}`, time: ms })
        addLog('error', `Endpoint returned ${r.status}`)
      }
    } catch (e: any) {
      setTest('health', { status: 'fail', error: e.message })
      addLog('error', `Connection failed: ${e.message}`)
    }
  }

  // ─── Test: Fire Order ───────────────────────────────────────────────────

  const fireOrder = async (scenario: string, orderType: string, variation?: any, addon?: any, discount?: any) => {
    const testName = `order_${scenario}`
    setTest(testName, { status: 'running' })
    const ts = Math.floor(Date.now() / 1000)
    const orderId = `FZ_LIVE_${scenario}_${ts}`
    const { date, time: timeStr, full } = now()

    const itemPrice = 439
    const cgstAmt = 10.98
    const sgstAmt = 10.98
    const finalPrice = discount ? itemPrice - discount : itemPrice
    const total = finalPrice + cgstAmt + sgstAmt

    addLog('request', `Firing order: ${orderId} (${scenario})`)

    const payload: any = {
      ...CREDS,
      orderinfo: {
        OrderInfo: {
          Restaurant: { details: { res_name: 'Dinematters DEMO', address: '', contact_information: '', restID: REST_ID } },
          Customer: { details: { email: 'test@flamezo.com', name: 'Live Test', address: 'Mumbai', phone: '9999999999', latitude: '', longitude: '' } },
          Order: { details: {
            orderID: orderId, preorder_date: date, preorder_time: timeStr,
            service_charge: '0', sc_tax_amount: '0', delivery_charges: '0', dc_tax_percentage: '0', dc_tax_amount: '0', dc_gst_details: [],
            packing_charges: '0', pc_tax_amount: '0', pc_tax_percentage: '0', pc_gst_details: [],
            order_type: orderType, ondc_bap: '', advanced_order: 'N', urgent_order: false, urgent_time: 0,
            payment_type: 'ONLINE', table_no: orderType === 'D' ? '1' : '', no_of_persons: '1',
            discount_total: discount ? String(discount) : '0', tax_total: String(cgstAmt + sgstAmt), discount_type: 'F',
            total: String(Math.round(total * 100) / 100), description: `Live test - ${scenario}`,
            created_on: full, enable_delivery: 1, min_prep_time: 20, callback_url: CALLBACK_URL
          }},
          OrderItem: { details: [{
            id: '10510067', name: 'Double Chicken Burger Combo', tax_inclusive: false, gst_liability: 'restaurant',
            item_tax: [{ id: '2201', name: 'CGST', tax_percentage: '2.5', amount: String(cgstAmt) }, { id: '2202', name: 'SGST', tax_percentage: '2.5', amount: String(sgstAmt) }],
            item_discount: discount ? String(discount) : '', price: String(itemPrice), final_price: String(finalPrice), quantity: '1', description: '',
            variation_name: variation?.name || '', variation_id: variation?.id || '',
            AddonItem: { details: addon ? [addon] : [] }
          }]},
          Tax: { details: [
            { id: '2201', title: 'CGST', type: 'P', price: '2.5', tax: String(cgstAmt), restaurant_liable_amt: String(cgstAmt) },
            { id: '2202', title: 'SGST', type: 'P', price: '2.5', tax: String(sgstAmt), restaurant_liable_amt: String(sgstAmt) }
          ]}
        },
        udid: '', device_type: 'Web'
      }
    }

    try {
      const start = Date.now()
      const r = await fetch(SAVE_ORDER_URL, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
      const data = await r.json()
      const ms = Date.now() - start

      if (String(data.success) === '1') {
        setTest(testName, { status: 'pass', response: `Order saved: ${orderId}`, time: ms })
        addLog('success', `${scenario}: Order saved (${ms}ms) — clientOrderID: ${orderId}`)
        setOrderIds(prev => [...prev, orderId])
      } else {
        setTest(testName, { status: 'fail', error: data.message || 'Unknown error', time: ms })
        addLog('error', `${scenario}: ${data.message}`)
      }
    } catch (e: any) {
      setTest(testName, { status: 'fail', error: e.message })
      addLog('error', `${scenario}: ${e.message}`)
    }
  }

  // ─── Test: Simulate Webhook ─────────────────────────────────────────────

  const simulateWebhook = async (name: string, payload: any, description: string) => {
    setTest(name, { status: 'running' })
    addLog('request', `Webhook: ${description}`)
    try {
      const start = Date.now()
      const r = await fetch(CALLBACK_URL, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
      const data = await r.json()
      const ms = Date.now() - start
      addLog('response', `${r.status} (${ms}ms) — ${JSON.stringify(data).slice(0, 200)}`)
      if (r.ok) {
        setTest(name, { status: 'pass', response: JSON.stringify(data), time: ms })
        addLog('success', `${description} — OK`)
      } else {
        setTest(name, { status: 'fail', error: `HTTP ${r.status}`, time: ms })
      }
    } catch (e: any) {
      setTest(name, { status: 'fail', error: e.message })
      addLog('error', `${description}: ${e.message}`)
    }
  }

  // ─── Run All ────────────────────────────────────────────────────────────

  const runAll5Orders = async () => {
    addLog('info', '━━━ Running all 5 order scenarios ━━━')
    await fireOrder('S1_ItemsTax', 'D')
    await fireOrder('S2_Addons', 'D', undefined, { id: '41110', name: 'Nugget & Sauce', group_name: 'Choice Of Sauce', price: '0', group_id: 9675, quantity: '1' })
    await fireOrder('S3_Variation', 'P', { name: 'Small', id: '8481' })
    await fireOrder('S4_Discount', 'D', undefined, undefined, 43.9)
    await fireOrder('S5_AddonVar', 'D', { name: 'Small', id: '8481' }, { id: '41110', name: 'Nugget & Sauce', group_name: 'Choice Of Sauce', price: '0', group_id: 9675, quantity: '1' })
    addLog('info', '━━━ All 5 scenarios fired ━━━')
  }

  const passCount = Object.values(results).filter(r => r.status === 'pass').length
  const failCount = Object.values(results).filter(r => r.status === 'fail').length
  const totalRun = passCount + failCount

  // ─── Render ─────────────────────────────────────────────────────────────

  return (
    <div className="flex h-[calc(100vh-64px)]">
      {/* Left Panel — Controls */}
      <div className="w-[480px] border-r overflow-y-auto p-5 space-y-5">
        {/* Header */}
        <div>
          <h1 className="text-xl font-bold flex items-center gap-2">
            Petpooja Live Testing
            <Badge variant="outline" className="text-xs">Sandbox</Badge>
          </h1>
          <p className="text-xs text-muted-foreground mt-1">June 3, 3 PM IST — restID: {REST_ID}</p>
          {totalRun > 0 && (
            <div className="flex gap-2 mt-2">
              <Badge variant="default" className="bg-green-500/10 text-green-600 border-green-200">{passCount} Passed</Badge>
              {failCount > 0 && <Badge variant="destructive">{failCount} Failed</Badge>}
            </div>
          )}
        </div>

        {/* 1. Health Check */}
        <TestCard
          icon={<Wifi className="w-4 h-4" />}
          title="1. Endpoint Health"
          description="Check callback URL is reachable"
          result={results.health}
          onRun={testEndpointHealth}
        />

        {/* 2. Menu Push */}
        <TestCard
          icon={<RefreshCw className="w-4 h-4" />}
          title="2. Menu Push/Sync"
          description="Simulate menu push from Petpooja"
          result={results.menu_push}
          onRun={() => simulateWebhook('menu_push', {
            restaurants: [{ restaurantid: '4479', active: '1', details: { menusharingcode: REST_ID } }],
            categories: [{ categoryid: '999', categoryname: 'Live Test Category', active: '1' }],
            items: [{ itemid: '999999', itemname: 'Live Test Item', price: '100', categoryid: '999', active: '1', itemallowvariation: '0', in_stock: '1' }],
            taxes: [{ taxid: '2201', taxname: 'CGST', tax: '2.5', active: '1' }, { taxid: '2202', taxname: 'SGST', tax: '2.5', active: '1' }],
            addongroups: [],
          }, 'Menu push with 1 category + 1 item')}
          note="Or let Shivam push from dashboard"
        />

        {/* 3. Item On/Off */}
        <TestCard
          icon={<ToggleLeft className="w-4 h-4" />}
          title="3. Item Stock Off"
          description="Toggle item out of stock"
          result={results.item_off}
          onRun={() => simulateWebhook('item_off', {
            restID: REST_ID, inStock: false, type: 'item', itemID: ['999999']
          }, 'Item stock OFF')}
        />
        <TestCard
          icon={<ToggleLeft className="w-4 h-4" />}
          title="   Item Stock On"
          description="Toggle item back in stock"
          result={results.item_on}
          onRun={() => simulateWebhook('item_on', {
            restID: REST_ID, inStock: true, type: 'item', itemID: ['999999']
          }, 'Item stock ON')}
        />

        {/* 4. Store On/Off */}
        <TestCard
          icon={<Store className="w-4 h-4" />}
          title="4. Store Close"
          description="Close store for online orders"
          result={results.store_close}
          onRun={() => simulateWebhook('store_close', {
            restID: REST_ID, store_status: '0', reason: 'Live testing'
          }, 'Store CLOSE')}
        />
        <TestCard
          icon={<Store className="w-4 h-4" />}
          title="   Store Open"
          description="Reopen store"
          result={results.store_open}
          onRun={() => simulateWebhook('store_open', {
            restID: REST_ID, store_status: '1'
          }, 'Store OPEN')}
        />

        {/* 5. Order Relay */}
        <div className="border rounded-lg p-4 space-y-3">
          <div className="flex items-center gap-2">
            <ShoppingCart className="w-4 h-4 text-primary" />
            <h3 className="text-sm font-bold">5. Order Relay — All 5 Scenarios</h3>
          </div>
          <p className="text-xs text-muted-foreground">Items+Tax, Addons, Variation, Discount, Addon+Variation</p>
          <Button onClick={runAll5Orders} className="w-full" size="sm">
            <Play className="w-3.5 h-3.5 mr-2" /> Fire All 5 Orders
          </Button>
          <div className="space-y-1">
            {['S1_ItemsTax', 'S2_Addons', 'S3_Variation', 'S4_Discount', 'S5_AddonVar'].map(s => (
              <div key={s} className="flex items-center gap-2 text-xs">
                <StatusIcon status={results[`order_${s}`]?.status || 'idle'} />
                <span className="flex-1">{s.replace('_', ': ')}</span>
                {results[`order_${s}`]?.time && <span className="text-muted-foreground">{results[`order_${s}`]?.time}ms</span>}
              </div>
            ))}
          </div>
        </div>

        {/* 6. Order Callbacks */}
        <div className="border rounded-lg p-4 space-y-3">
          <div className="flex items-center gap-2">
            <Truck className="w-4 h-4 text-primary" />
            <h3 className="text-sm font-bold">6. Order Status Callbacks</h3>
          </div>
          <p className="text-xs text-muted-foreground">Simulate Petpooja accepting/delivering orders</p>
          <div className="grid grid-cols-3 gap-2">
            {[
              { label: 'Accept', status: '1', color: 'bg-green-500/10 text-green-600 hover:bg-green-500/20' },
              { label: 'Ready', status: '5', color: 'bg-blue-500/10 text-blue-600 hover:bg-blue-500/20' },
              { label: 'Dispatch', status: '4', color: 'bg-orange-500/10 text-orange-600 hover:bg-orange-500/20' },
              { label: 'Deliver', status: '10', color: 'bg-emerald-500/10 text-emerald-600 hover:bg-emerald-500/20' },
              { label: 'Cancel', status: '-1', color: 'bg-red-500/10 text-red-600 hover:bg-red-500/20' },
            ].map(cb => (
              <Button key={cb.status} variant="ghost" size="sm"
                className={cn("text-xs h-8", cb.color)}
                onClick={() => {
                  const oid = orderIds[orderIds.length - 1] || 'FZ_LIVE_TEST'
                  simulateWebhook(`callback_${cb.status}`, {
                    restID: REST_ID, clientorderID: oid, orderID: oid,
                    status: cb.status, cancel_reason: cb.status === '-1' ? 'Testing cancel' : '',
                    minimum_prep_time: '15'
                  }, `Callback: ${cb.label} (status=${cb.status}) for ${oid}`)
                }}>
                {cb.label}
              </Button>
            ))}
          </div>
          {orderIds.length > 0 && (
            <p className="text-[10px] text-muted-foreground">Last order: {orderIds[orderIds.length - 1]}</p>
          )}
        </div>

        {/* Fired Order IDs */}
        {orderIds.length > 0 && (
          <div className="border rounded-lg p-4 space-y-2">
            <h3 className="text-sm font-bold flex items-center gap-2">
              <Clock className="w-4 h-4" /> Fired Orders ({orderIds.length})
            </h3>
            <div className="space-y-1">
              {orderIds.map((id, i) => (
                <div key={i} className="flex items-center gap-2 text-xs font-mono bg-muted/30 px-2 py-1 rounded">
                  <span className="flex-1">{id}</span>
                  <button onClick={() => { navigator.clipboard.writeText(id); toast.success('Copied') }}
                    className="text-muted-foreground hover:text-foreground"><Copy className="w-3 h-3" /></button>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Right Panel — Live Log */}
      <div className="flex-1 flex flex-col bg-zinc-950 text-zinc-200">
        <div className="flex items-center justify-between px-4 py-2 border-b border-zinc-800">
          <div className="flex items-center gap-2">
            <Terminal className="w-4 h-4 text-green-400" />
            <span className="text-sm font-bold text-zinc-300">Live Log</span>
            <Badge variant="outline" className="text-[10px] h-4 border-zinc-700 text-zinc-500">{logs.length} entries</Badge>
          </div>
          <Button variant="ghost" size="sm" className="text-xs text-zinc-500 hover:text-zinc-300 h-6"
            onClick={() => setLogs([])}>Clear</Button>
        </div>
        <div className="flex-1 overflow-y-auto p-4 font-mono text-xs space-y-0.5">
          {logs.length === 0 && (
            <p className="text-zinc-600 text-center py-10">Run a test to see live output here...</p>
          )}
          {logs.map((log, i) => (
            <div key={i} className={cn("flex gap-2", {
              'text-zinc-500': log.type === 'info',
              'text-cyan-400': log.type === 'request',
              'text-zinc-400': log.type === 'response',
              'text-green-400': log.type === 'success',
              'text-red-400': log.type === 'error',
            })}>
              <span className="text-zinc-600 shrink-0">{log.time}</span>
              <span className="shrink-0">{
                log.type === 'request' ? '>>>' :
                log.type === 'response' ? '<<<' :
                log.type === 'success' ? ' OK' :
                log.type === 'error' ? 'ERR' : '---'
              }</span>
              <span className="break-all">{log.message}</span>
            </div>
          ))}
          <div ref={logsEndRef} />
        </div>
      </div>
    </div>
  )
}



