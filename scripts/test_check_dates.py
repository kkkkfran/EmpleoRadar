import asyncio
from datetime import datetime

import aiohttp

from app.sources.bne import BNESource
from app.sources.chiletrabajos import ChileTrabajosSource
from app.sources.inacap import InacapSource


async def main():
    cutoff = datetime(2026, 10, 13)
    async with aiohttp.ClientSession() as session:
        # BNE
        bne = BNESource()
        bne_jobs = await bne.fetch_jobs(session)
        print("BNE fetched:", len(bne_jobs))
        bne_valid = [j for j in bne_jobs if (j.published_at or datetime.now()) >= cutoff]
        print("BNE >= 13-Oct:", len(bne_valid))
        if bne_jobs:
            print("BNE sample 1 date:", bne_jobs[0].published_at, "Title:", bne_jobs[0].title)

        # INACAP
        inacap = InacapSource()
        inacap_jobs = await inacap.fetch_jobs(session)
        print("INACAP fetched:", len(inacap_jobs))
        inacap_valid = [j for j in inacap_jobs if (j.published_at or datetime.now()) >= cutoff]
        print("INACAP >= 13-Oct:", len(inacap_valid))
        if inacap_jobs:
            print("INACAP sample 1 date:", inacap_jobs[0].published_at, "Title:", inacap_jobs[0].title)

        # ChileTrabajos
        ct = ChileTrabajosSource()
        ct_jobs = await ct.fetch_jobs(session)
        print("ChileTrabajos fetched:", len(ct_jobs))
        ct_valid = [j for j in ct_jobs if (j.published_at or datetime.now()) >= cutoff]
        print("ChileTrabajos >= 13-Oct:", len(ct_valid))
        if ct_jobs:
            print("CT sample 1 date:", ct_jobs[0].published_at, "Title:", ct_jobs[0].title)

if __name__ == "__main__":
    asyncio.run(main())

