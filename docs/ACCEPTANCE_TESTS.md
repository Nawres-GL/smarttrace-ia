# SmartTrace Phase 2 — Acceptance checklist

## Preconditions
- MongoDB Atlas development cluster, configured database credentials, admin bootstrapped.
- The two original Excel files are present in `data/` but left **unchanged**.
- Backend and frontend running on 127.0.0.1; admin logged in.

## A. Historical data
- [ ] Open historical lot `13766`; production and delivery information are linked by exactly five digits.
- [ ] Multiple full Excel references with the same five-digit key are shown, not silently merged.
- [ ] Article differences are warnings, not rejected matches.
- [ ] Verify original `.xlsx` files are byte-for-byte unchanged.
- [ ] User without admin role does not have access to historical customer records.

## B. Access management
- [ ] Bad password returns HTTP 401.
- [ ] Anonymous access to operational lots returns HTTP 401.
- [ ] Non-admin user assigned S01 cannot access a lot at another site.
- [ ] Production employee cannot approve quality or ship an order.
- [ ] Admin can create new sites and users through authorized Swagger endpoints.
- [ ] JWT secret and Atlas credentials are not visible in Git or React assets.

## C. Stock integrity
- [ ] Cannot sow more seeds than unallocated supply.
- [ ] Cannot register more germinated plants than sown seeds.
- [ ] Germination can only be registered once for an ordinary seed lot.
- [ ] Transferring 500 plants from location A to B changes locations but not total stock.
- [ ] Cannot transfer/loss more than free stock at a location.
- [ ] Losses invalidate the previous quality release.
- [ ] Treatment triggers a new quality check in this conservative pilot.
- [ ] Grafting consumes two distinct parent lots, creates a child lot and records the success/loss counts.
- [ ] Grafted child cannot be delivered without its own quality approval.
- [ ] Preparation fails when lot is not approved or commercializable capacity is insufficient.
- [ ] Delivery fails when no matching preparation exists, or quantity exceeds reserved balance.
- [ ] Partial deliveries preserve the remaining reservation.
- [ ] Returns create a quarantined child lot; returned plants aren't silently reintroduced to saleable inventory.
- [ ] Retrying the same POST with an identical `Idempotency-Key` does not change stock twice.
- [ ] Concurrent conflicting mutations result in one valid outcome, not negative balances.

## D. History and QR
- [ ] Each validated operation has an authenticated actor ID, site, UTC timestamp, event type and details.
- [ ] Each event has a deterministic hash and a blockchain outbox entry.
- [ ] Before a real Fabric commit, UI says **non certifié / en attente** (never verified).
- [ ] Scanned QR leads to a **protected** lot dossier; unauthenticated users must log in first.
- [ ] Activating an Excel historical lot requires admin-provided real stock, exact reference and justification.
- [ ] Historical records are not presented as new Blockchain events.

## E. Deployment gate (not yet passed)
- [ ] Customer permissions and source-site mapping approved by Royal Plants.
- [ ] Audit-verified backups and test restoration procedure.
- [ ] HTTPS, secrets rotation, session management, logging, error monitoring, rate limiting.
- [ ] Data retention policy and privacy review, especially customer and employee data.
- [ ] Tested safe concurrency, offline synchronization and real Fabric certification.
- [ ] Management signs off on stock, grafting, commercial quantities and quality workflows.
