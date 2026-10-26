def totalMarks(*marks):
    return sum(*marks)

def averageMarks(*marks):
    return sum(*marks) / len(*marks)

def Grades(Avg):
    if Avg > 100:
        return "Marks can't exceed 100"
    if Avg >=80:
        return "A" 
    elif  Avg >= 70:
        return "B"
    elif Avg >= 60:
        return "C"
    elif Avg >= 50:
        return "D"
    elif Avg >= 40:
        return "E"
    elif Avg <= 39:
        return "F"
    elif Avg < 0:
        "Marks can't be negative"

students = []
passed = 0
failed = 0

print(f"=========== School Reporting System ===========")
count = int(input(f"Enter number of students you wanna insert: "))
for i in range(1, count + 1):
    print(f"Insert student number {i}")
    studentNames = input(f"Enter the names of student:  ")
    print(f"Now you are going to Enter marks for {studentNames}")
    Mathematics = int(input(f"Enter marks in math : "))
    English = int(input(f"Enter marks in english : "))
    Python = int(input(f"Enter marks in python : "))
    Sum = totalMarks((Mathematics,English,Python))
    Avg = averageMarks((Mathematics,English,Python))kir
    Grade = Grades(Avg)
    if Avg >= 50:
        passed += 1    
    else:
        failed += 1
    students.append((studentNames, Mathematics,English,Python,Sum,Avg,Grade))

print("Here are your Students Report")
print("==============================")
for studentName, Mathematics,English,Python,Sum,Avg,Grade in students:
    print(f"Sudent Name: {studentName} | Math: {Mathematics} | Eng: {English} | Py: {Python} | Total: {Sum} | Avg: {Avg:.2f} | Grade: {Grade}")

print(f"Class summary: Passed = {passed} | Failed = {failed}")

