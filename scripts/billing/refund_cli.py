#!/usr/bin/env python3
"""Server-local customer-service entry point for reviewed refunds.

This command is never packaged into the desktop product and the corresponding
HTTP route is blocked by the public Nginx configuration.
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _amount_fen(value: str) -> int:
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError("金额格式无效") from exc
    if amount.as_tuple().exponent < -2 or amount < Decimal("0.01"):
        raise argparse.ArgumentTypeError("退款金额必须为正数且最多两位小数")
    fen = int(amount * 100)
    if fen > 10_000_000:
        raise argparse.ArgumentTypeError("单次退款不能超过￥100,000")
    return fen


def main() -> int:
    parser = argparse.ArgumentParser(description="GO CLAW 客服审核退款（仅服务器本机）")
    parser.add_argument("--order-id", required=True)
    parser.add_argument("--amount-cny", required=True, type=_amount_fen)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--evidence-ref", action="append", required=True)
    parser.add_argument("--operator-id", required=True)
    parser.add_argument("--approver-id", required=True)
    parser.add_argument(
        "--idempotency-key",
        help="结果未知时必须复用上一次显示的 key",
    )
    parser.add_argument(
        "--token-file",
        type=Path,
        default=Path("/etc/go-claw-billing/credentials/admin_token"),
    )
    parser.add_argument(
        "--endpoint",
        default="http://127.0.0.1:9200/internal/admin/refunds",
    )
    args = parser.parse_args()
    if args.operator_id == args.approver_id:
        parser.error("发起人与复核人必须不同")
    token = args.token_file.read_text("utf-8").strip()
    if len(token) < 32:
        raise RuntimeError("客服退款凭据无效")
    payload = json.dumps(
        {
            "orderId": args.order_id,
            "amountFen": args.amount_cny,
            "reason": args.reason,
            "evidenceRefs": args.evidence_ref,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    idempotency_key = args.idempotency_key or secrets.token_urlsafe(24)
    request = Request(
        args.endpoint,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Idempotency-Key": idempotency_key,
            "X-Operator-Id": args.operator_id,
            "X-Approver-Id": args.approver_id,
        },
    )
    try:
        with urlopen(request, timeout=15) as response:
            result = json.load(response)
    except HTTPError as exc:
        print(f"退款申请未受理：HTTP {exc.code}", file=sys.stderr)
        return 2
    except (URLError, TimeoutError):
        print(
            "退款结果未知，勿盲目重复提交；核查后如需重试必须复用 "
            f"--idempotency-key {idempotency_key}",
            file=sys.stderr,
        )
        return 3
    print(
        f"退款流程已受理：refundId={result['refundId']} "
        f"amountFen={result['amountFen']} status={result['status']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
