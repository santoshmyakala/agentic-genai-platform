# Orders dead-letter queue (serverless intake)

## Symptoms
AWS: the CloudWatch alarm orders-dlq-not-empty fires (ApproximateNumberOfMessagesVisible > 0 on orders-dlq). Azure: the alert alert-orders-dead-letters fires (DeadletteredMessages > 0 on the orders Service Bus queue).

## Why messages dead-letter
A message moves to the DLQ after 5 failed processing attempts (maxReceiveCount on SQS, max_delivery_count on Service Bus). Common causes: a DynamoDB or Cosmos DB throttle that outlasted retries, a schema change producing records the processor cannot parse, or a deployment that broke the processor.

## Actions
1. Inspect a sample of DLQ messages and the processor logs (structured JSON logs; X-Ray or Application Insights traces) for the failure reason.
2. Fix the root cause first. Redriving before the fix just sends messages back to the DLQ.
3. Redrive: SQS supports DLQ redrive to the source queue; on Service Bus, receive from the $DeadLetterQueue sub-queue and resend.
4. Writes are idempotent (conditional put / upsert by id), so redriving duplicates is safe.
