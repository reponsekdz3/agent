def item_total(price, quantity):
    return price * quantity

def apply_discount(total, rate=0.05):
    if total > 20000:
        return total * rate
    return 0

def calculate_vat(amount):
    return amount * 0.18

running_total = 0
items = []

print("=== Kigali Market Billing System ===")

while True:
    try:
        num_items_target = int(input("How many different items are you buying? "))
        if num_items_target > 0:
            break
        else:
            print("Please enter a number greater than 0.")
    except ValueError:
        print("Error: Please enter a valid whole number.")

print("\nEnter item details (type 'done' as item name to finish early)\n")

item_count = 0

while True:

    if item_count >= num_items_target:
        print(f"\nReached the limit of {num_items_target} items.")
        break

    name = input("Item name: ").strip()

    if name.lower() == "done":
        break

    try:
        price = float(input("Unit price (RWF): "))
        quantity = float(input("Quantity: "))
    except ValueError:
        print("Error: Please enter valid numbers.\n")
        continue

    if price <= 0 or quantity <= 0:
        print("Error: Price and quantity must be greater than 0. Skipping this item.\n")
        continue

    cost = item_total(price, quantity)
    running_total += cost
    items.append((name, price, quantity, cost))
    
    item_count += 1 

    print(f"  → {name}: {price:.0f} × {quantity:.0f} = {cost:.0f} RWF\n")

discount = apply_discount(running_total)
amount_after_discount = running_total - discount
vat = calculate_vat(amount_after_discount)
final_total = amount_after_discount + vat

print("\n" + "="*40)
print(f"Subtotal:          {running_total:.0f} RWF")
print(f"Discount (5%):     {discount:.0f} RWF")
print(f"VAT (18%):         {vat:.0f} RWF")
print(f"TOTAL TO PAY:      {final_total:.0f} RWF")
print("="*40)

while True:
    try:
        paid = float(input("\nAmount paid by customer: "))
        break
    except ValueError:
        print("Error: Please enter a valid number.")

if paid < final_total:
    print("Insufficient payment")
else:
    change = paid - final_total

    print("\n" + "="*45)
    print("           KIGALI MARKET RECEIPT")
    print("="*45)

    for name, price, qty, cost in items:
        print(f"Item: {name:<12} | Price: {price:>6.0f} | Qty: {qty:>4.0f} → {cost:>8.0f} RWF")

    print("-"*45)
    print(f"Subtotal:               {running_total:>10.0f} RWF")
    print(f"Discount (5%):          {discount:>10.0f} RWF")
    print(f"VAT (18%):              {vat:>10.0f} RWF")
    print(f"TOTAL:                  {final_total:>10.0f} RWF")
    print(f"Paid:                   {paid:>10.0f} RWF")
    print(f"Change:                 {change:>10.0f} RWF")
    print("="*45)
    print("Thank you for shopping with us!")
