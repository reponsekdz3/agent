balance = 50000

def CalculateFee(amount):
    if amount < 1001:
        return 0
    elif amount <= 10000:
        return 100
    else: 
        return amount *1 /100

def CheckBalance(balance):

    return balance

def DepositCash(amount, balance):
    newBalance = amount + balance
    return newBalance

def withdrawcash(amount, balance):
    newBalance = balance - amount
    
    return newBalance

def sendmoney(sentmount,balance):
    transactions = balance - sentmount


    return transactions
while True:
    print("Welcome to MOMO System here are options to choose from")
    print("1. Balance, 2. Deposit, 3. Withdraw, 4. Send Money, 5. Exit")
    choice = int(input("Choose options above: "))

    if choice == 1:
        print(f"Dear user, your current balance is: {CheckBalance(balance)}")
    elif choice == 2:
        depoAmount = int(input("Enter amount to deposit: "))
        newBalance = DepositCash(depoAmount, balance) if depoAmount > 0 else "U can't deposit zero amount"
        balance = newBalance
        print(f"your new balance now is : {newBalance}")
    elif choice == 3:

        print(f" you want to withdraw, your current balance is: {CheckBalance(balance)}")
        withdrawamount =int(input(f"enter amount to withdraw : "))
        balance = newBalance
        newbalance = withdrawcash(withdrawamount,balance) if withdrawamount > 0 else "u can not withodrow money less than zero"
        print(newbalance)
    elif choice == 4:
        print(f"you are going to send money ")
        sendnumber = int(input(f" enter phone number you are going to send money to : "))
        sentamount =int(input(f" enter amonut you want to send to this number {sendnumber}  :"))
        fee = CalculateFee(sentamount)
        print (f"removed fee is : {sentamount+fee}")
        newbalance = sendmoney (sentamount,balance)
        balance = newbalance
        print(f"you remains {newbalance} in your wallet")

    elif choice == 5:
        print(f"you exited .send us feed back about our services if is correct ")

    else :
        print("invald option")
        