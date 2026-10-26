name=input("enter your names here")
marks = float(input("enter marks 0 to 100"))

if marks < 0 or marks >100:
    print ("invalidmarks!enter correct marks must be 0 to 100")
else:
    if marks >=80:
        grade ="A"
    elif marks >=60:
        grade ="B"
    elif marks >=50:
        grade ="c"
    else:
        grade ="d"

print(f"student: {name}")
print(f"marks: {marks}")
print(f"grade: {grade}")