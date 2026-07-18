import asyncio
import pytest

@pytest.mark.asyncio
async def test_concurrent_transfers_cannot_double_spend(session_factory):
    # --- STEP 1: DO SETUP SEQUENTIALLY ---
    # Create a session just to write the initial balances to the DB, then CLOSE it.
    async with session_factory() as setup_session:
        acc_a = Account(id=201, currency="USD", balance=500.0, type="customer")
        acc_b = Account(id=202, currency="USD", balance=0.0, type="customer")
        setup_session.add_all([acc_a, acc_b])
        await setup_session.commit() 
    
    # At this point, setup_session is closed. The DB has our starting state.

    # --- STEP 2: DEFINE THE WORKER ---
    # This worker function must spawn its OWN session from the factory
    async def run_transfer(amount):
        async with session_factory() as worker_session:
            # Put your actual transfer logic/API call here, using worker_session!
            # Example:
            # await transfer_service.execute(worker_session, from_id=201, to_id=202, amount=amount)
            await worker_session.commit()

    # --- STEP 3: RUN CONCURRENTLY ---
    # Now we fire off multiple workers at the exact same time. 
    # Because each worker has its own "async with session_factory()", 
    # asyncpg won't throw "another operation is in progress"!
    await asyncio.gather(
        run_transfer(300.0),
        run_transfer(300.0),
        return_exceptions=True  # Helpful so one failure doesn't crash the whole gather
    )

    # --- STEP 4: VERIFY RESULTS ---
    # Open a fresh session to check that double spending was prevented
    async with session_factory() as verify_session:
        # Assertions go here (e.g., Account A's balance shouldn't be negative)
        ...