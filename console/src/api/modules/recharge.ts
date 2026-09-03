import { request } from "../request";

export interface RechargeConfig {
  enabled: boolean;
  currency: "CNY";
  pricingVersion: string;
  computeUnitsPerFen: 50000;
  displayRate: "￥1对应500万算力";
  minAmountFen: 100;
  maxAmountFen: 10000000;
  amountStepFen: 1;
  dailyLimitFen: number | null;
  presetsFen: [1000, 5000, 10000, 20000];
  termsVersion: string;
}

export interface RechargeBalance {
  grantedComputeUnits: number;
  remainingComputeUnits: number;
  percent: number;
  observedAt: string;
}

export type RechargeOrderStatus =
  | "PENDING_PAYMENT"
  | "CREDITING"
  | "SUCCEEDED"
  | "EXPIRED"
  | "CLOSED"
  | "REVIEW_REQUIRED"
  | "REFUNDING"
  | "REFUNDED";

export interface RechargeOrder {
  orderId: string;
  merchantOrderNo: string;
  amountFen: number;
  amountCny: string;
  computeUnits: number;
  pricingVersion: string;
  status: RechargeOrderStatus;
  codeUrl?: string | null;
  expiresAt: string;
  createdAt: string;
  updatedAt: string;
}

export interface RechargeLedgerEntry {
  entryId: string;
  orderId: string;
  kind: "PAYMENT" | "QUOTA_CREDIT" | "QUOTA_REVERSAL" | "REFUND";
  amountFen: number;
  computeUnits: number;
  occurredAt: string;
}

export const rechargeApi = {
  config: () => request<RechargeConfig>("/console/recharge/config"),
  balance: () => request<RechargeBalance>("/console/recharge/balance"),
  createOrder: (
    amountFen: number,
    acceptedTermsVersion: string,
    idempotencyKey: string,
  ) =>
    request<RechargeOrder>("/console/recharge/orders", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({ amountFen, acceptedTermsVersion }),
      timeout: 20_000,
    }),
  order: (orderId: string) =>
    request<RechargeOrder>(`/console/recharge/orders/${orderId}`),
  ledger: () =>
    request<{ items: RechargeLedgerEntry[]; nextCursor: string | null }>(
      "/console/recharge/ledger?page_size=20",
    ),
};
