class Heavy:
    def __init__(self, name, hp, damage, enhp):
        self.name = name
        self.hp = hp
        self.enhp = enhp
        self.damage = damage

    def attack(self, enhp):
        print('атака почалася')
    
    def flee(self):
        print('ти намагаєшся втекти')

    def check(self):
        print('перевірка')


class Killing(Heavy):
    def __init__(self, name, hp, damage, enhp):
        super().__init__(name, hp, damage, enhp)
    
    def attack(self, enhp):
        for i in range(5):
            self.enhp -= 5
        print(f'HP ворогів становить: {self.enhp}')


class GiveUp(Heavy):
    def flee(self,name):
        print(self.name, 'але ворог тебе наздогнав і заарештував')


class Checking(Heavy):
    def __init__(self, name, hp, enhp):
        super().__init__(name, hp, 0, enhp)

    def check(self,enhp):
        print(self.name, f'| HP ворога {enhp}')


# =============================================================

class Warrior:
    def __init__(self, name, hp, damage, enhp):
        self.name = name
        self.hp = hp
        self.enhp = enhp
        self.damage = damage

    def attack(self, enhp):
        print('атака почалася')
    
    def flee(self):
        print('ти намагаєшся втекти')

    def check(self):
        print('перевірка')


class Warrior_killing(Heavy):
    def __init__(self, name, hp, damage, enhp):
        super().__init__(name, hp, damage, enhp)
    
    def attack(self, enhp):
        for i in range(5):
            self.enhp -= 10
        print(f'HP ворогів становить: {self.enhp}')


class Warrior_giveUp(Heavy):
    def flee(self,name):
        print(name,'але ворог тебе наздогнав і заарештував')


class Warrior_checking(Heavy):
    def __init__(self, name, hp, enhp):
        super().__init__(name, hp, 0, enhp)

    def check(self,enhp):
        print(self.name, f'HP ворога {enhp}')


player1 = Killing('гравець1', 250, 5, 100)
player1_5 = Checking('гравець1', 250, 100)
flee = GiveUp('гравець1', 250, 5, 100)
player2 = Warrior_killing('гравець2', 100, 7,250)
player2_5 = Warrior_checking('гравець2', 100,250)

while True:
    input1 = int(input(
        "Гравець 1, обери дію:\n"
        "1 — Атакувати\n"
        "2 — Втекти\n"
        "3 — Перевірити HP\n"
        "4 — Вийти\n"
        "твій вибір: "
    ))

    if input1 == 1:
        player1.attack(player1.enhp)
        if player1.enhp <= 0:
            print("ворог помер")
            break

    elif input1 == 2:
        flee.flee(player1.name)
        break
    elif input1 == 3:
        player1_5.check(player1.enhp)
    else:
        break

    input2 = int(input(
        "Гравець 2, обери дію:\n"
        "1 — Атакувати\n"
        "2 — Втекти\n"
        "3 — Перевірити HP\n"
        "4 — Вийти\n"
        "твій вибір: "
    ))

    if input2 == 1:
        player2.attack(player2.enhp)
        if player2.enhp <= 0:
            print("ворог помер")
            break
        
    elif input2 == 2:
        flee.flee(player2.name)
        break
    elif input2 == 3:
        player2_5.check(player2.enhp)
    else:
        break

    