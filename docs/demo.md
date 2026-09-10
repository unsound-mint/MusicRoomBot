# Demo

This document shows sanitized example flows. It avoids real chat IDs, private
links, invite links, and room coordinates.

## Member Booking Flow

```text
Member opens the bot
-> Bot shows the main menu:
   Book a slot
   My bookings
   Schedule
   Equipment
   Rules

Member selects "Book a slot"
-> Bot shows available days.

Member selects a day
-> Bot shows available hourly slots.

Member selects "Tuesday 18:00"
-> Bot creates the booking if the slot is still available.
-> Bot replies with booking details and a calendar action.
```

Important behavior:

- The service checks availability before booking.
- The database unique constraint prevents double-booking under race conditions.
- Booking flows are guarded by backpressure so bursts do not exhaust the
  database pool.

## Consecutive Booking Reminder Flow

```text
Member books Tuesday 18:00 and Tuesday 19:00
-> Bot treats the bookings as one consecutive chain for reminders.

Two hours before 18:00
-> Bot sends one reminder for the 18:00 booking.

Fifteen minutes before 18:00
-> Bot sends the final reminder for the 18:00 booking.
```

The reminder service intentionally sends reminders only for the first slot in a
consecutive chain, avoiding duplicate notifications for back-to-back bookings.

## Attendance Check-In Flow

```text
Member has an active booking
-> Bot prompts for location when check-in is needed.

Member shares location
-> Bot compares the location with the configured room center and radius.

Location is inside the radius and before the late deadline
-> Bot marks attendance as verified.

Location is outside the radius or too late
-> Bot keeps attendance unverified and explains the issue.
```

The deployment owner configures the radius, center point, and late window through
runtime config.

## Booking Cancellation Flow

```text
Member opens "My bookings"
-> Bot lists active bookings.

Member selects a booking
-> Bot shows actions for that booking.

Member selects cancel
-> Bot cancels the booking if cancellation is still allowed.
-> Bot updates the booking list.
```

If another action already changed the booking, the handler renders a stale-state
message instead of failing silently.

## Swap Flow

```text
Member opens a booking
-> Bot offers swap-related actions.

Member creates a swap offer
-> Bot records the offer and exposes it to eligible users.

Another member accepts
-> Service validates that both bookings and users are still eligible.
-> Bot applies the swap and updates both users.
```

Swap handlers are written defensively because Telegram callback buttons may be
pressed after the underlying booking or offer has changed.

## Equipment Request Flow

```text
Member opens "Equipment"
-> Bot starts an equipment request.

Member enters request details and date range
-> Bot stores the request.
-> Bot posts the request for admin review.

Admin approves
-> Bot posts the approved request to the configured member topic if available.
```

The request keeps review message IDs and post message IDs so admins can update
or clean up related Telegram messages later.

## Admin Configuration Flow

```text
Admin opens the admin panel
-> Bot shows configuration, users, bookings, equipment, and warning tools.

Admin opens configuration
-> Bot shows runtime settings.

Admin changes late check-in window to 15 minutes
-> Bot validates and stores the value in the config table.
-> Runtime config cache is invalidated for the changed key.
```

Operational values can be changed without redeploying the service.

## Suggested Screenshots

If you publish screenshots, use a test bot and a test group. Redact or avoid:

- bot token
- chat IDs and topic IDs
- member names/usernames unless they consent
- invite links
- private form URLs
- real room coordinates

Good screenshot set:

- main menu
- available slot selection
- booking confirmation
- my bookings view
- attendance check-in response
- admin config screen
- equipment request review
