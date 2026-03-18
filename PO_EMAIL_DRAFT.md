# Focused PO Email Draft

Subject: Confirming request reconciliation rules for section-offerings scheduling

Hi [PO Name],

We’ve implemented the new section-offerings scheduling flow and want to confirm the request reconciliation rules before we lock them in.

Today, the scheduler does three things before assignment:
- drops requests for course codes that have no matching section offering,
- collapses duplicate weekday-variant requests to a single schedulable request per student,
- treats lunch-family requests (`2912*`) specially by marking the extra variant as an inferred semester 2 placement.

To make sure this matches your expectations, can you confirm:
1. whether non-offered requests should always be dropped,
2. whether weekday variants should always collapse to one request per student,
3. whether the current lunch-family handling reflects the intended semester 1 / semester 2 behavior.

We are already outputting these removals in `dropped_by_reason.txt`, so once you confirm the rules we can finalize both the scheduling logic and the review workflow.

Thanks,
[Your Name]
