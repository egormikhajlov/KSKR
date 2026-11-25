using System;

class Program
{
    static void Main()
    {
        // ==========================================
        // 1. ИСХОДНЫЕ ДАННЫЕ
        // ==========================================
        double E = 7.0e10;   // Модуль Юнга (алюминий), Па
        double nu = 0.33;     // Коэффициент Пуассона
        int s = 2;            // Кол-во перемещений на узел

        // Координаты узлов: (x, y). Пластина 4 x 1.5
        double[,] nodes = new double[,]
        {
            { 0.0, 0.0 }, // Узел 0
            { 2.0, 0.0 }, // Узел 1
            { 4.0, 0.0 }, // Узел 2
            { 0.0, 1.5 }, // Узел 3
            { 2.0, 1.5 }, // Узел 4
            { 4.0, 1.5 }  // Узел 5
        };

        // Элементы: 034, 041, 145, 152 (обход против часовой)
        int[,] elements = new int[,]
        {
            { 0, 3, 4 },
            { 0, 4, 1 },
            { 1, 4, 5 },
            { 1, 5, 2 }
        };

        int numNodes = nodes.GetLength(0);       // 6
        int numElements = elements.GetLength(0);    // 4
        int totalDof = numNodes * s;             // 12

        // ==========================================
        // 2. МАТРИЦА УПРУГОСТИ [E] (3x3)
        // ==========================================
        double[,] E_mat = new double[3, 3];
        double factor = E / (1.0 - nu * nu);

        E_mat[0, 0] = factor; E_mat[0, 1] = factor * nu; E_mat[0, 2] = 0.0;
        E_mat[1, 0] = factor * nu; E_mat[1, 1] = factor; E_mat[1, 2] = 0.0;
        E_mat[2, 0] = 0.0; E_mat[2, 1] = 0.0; E_mat[2, 2] = factor * ((1.0 - nu) / 2.0);

        // ==========================================
        // 3. ГЛОБАЛЬНАЯ МАТРИЦА ЖЁСТКОСТИ
        // ==========================================
        double[,] K_global = new double[totalDof, totalDof];

        // ==========================================
        // 4. РАСЧЁТ ГЛОБАЛЬНОЙ МАТРИЦЫ
        // ==========================================
        for (int e = 0; e < numElements; e++)
        {
            int n0 = elements[e, 0];
            int n1 = elements[e, 1];
            int n2 = elements[e, 2];

            double x0 = nodes[n0, 0], y0 = nodes[n0, 1];
            double x1 = nodes[n1, 0], y1 = nodes[n1, 1];
            double x2 = nodes[n2, 0], y2 = nodes[n2, 1];

            // Площадь A = 1/2 * det
            double det = (x1 * y2 - x2 * y1) - (x0 * y2 - x2 * y0) + (x0 * y1 - x1 * y0);
            double A = Math.Abs(0.5 * det);

            // Коэффициенты b, c
            double bi = y2 - y1;
            double bj = y1 - y0;
            double bm = y0 - y2;

            double ci = x1 - x2;
            double cj = x0 - x1;
            double cm = x0 - x2;

            // Матрица [B] (3x6)
            double[,] B = new double[3, 6]
            {
                { bi,  0, bj,  0, bm,  0 },
                {  0, ci,  0, cj,  0, cm },
                { ci, bi, cj, bj, cm, bm }
            };

            // [B]^T * [E] * [B]
            double[,] BT = Transpose(B);
            double[,] EB = Multiply(E_mat, B);
            double[,] BTEB = Multiply(BT, EB);

            // Локальная матрица: [k] = [B]^T * [E] * [B] / (4A)
            double[,] k_local = new double[6, 6];
            for (int r = 0; r < 6; r++)
                for (int c = 0; c < 6; c++)
                    k_local[r, c] = BTEB[r, c] / (4.0 * A);   // <-- ИСПРАВЛЕНО

            Console.WriteLine($"--- Локальная матрица [k], элемент ({n0}{n1}{n2}), A = {A:F4} ---");
            PrintMatrix(k_local);

            // Степени свободы: [2n, 2n+1]
            int[] dofs = new int[6]
            {
                2 * n0, 2 * n0 + 1,
                2 * n1, 2 * n1 + 1,
                2 * n2, 2 * n2 + 1
            };

            for (int r = 0; r < 6; r++)
                for (int c = 0; c < 6; c++)
                    K_global[dofs[r], dofs[c]] += k_local[r, c];
        }

        // ==========================================
        // 5. ВЫВОД ГЛОБАЛЬНОЙ МАТРИЦЫ
        // ==========================================
        Console.WriteLine("\n==================================================");
        Console.WriteLine("ИТОГОВАЯ ГЛОБАЛЬНАЯ МАТРИЦА ЖЁСТКОСТИ (12x12):");
        Console.WriteLine("==================================================\n");
        PrintMatrix(K_global);

        Console.WriteLine("Готово. Нажмите Enter...");
        Console.ReadLine();
    }

    // ---------- Вспомогательные функции ----------

    static double[,] Multiply(double[,] A, double[,] B)
    {
        int rA = A.GetLength(0);
        int cA = A.GetLength(1);
        int cB = B.GetLength(1);
        double[,] res = new double[rA, cB];

        for (int i = 0; i < rA; i++)
            for (int j = 0; j < cB; j++)
                for (int k = 0; k < cA; k++)
                    res[i, j] += A[i, k] * B[k, j];

        return res;
    }

    static double[,] Transpose(double[,] A)
    {
        int r = A.GetLength(0);
        int c = A.GetLength(1);
        double[,] res = new double[c, r];

        for (int i = 0; i < r; i++)
            for (int j = 0; j < c; j++)
                res[j, i] = A[i, j];

        return res;
    }

    static void PrintMatrix(double[,] matrix)
    {
        int rows = matrix.GetLength(0);
        int cols = matrix.GetLength(1);

        Console.Write("       ");
        for (int j = 0; j < cols; j++)
            Console.Write($"[{j,2}]        ");
        Console.WriteLine("\n" + new string('-', cols * 13));

        for (int i = 0; i < rows; i++)
        {
            Console.Write($"[{i,2}] ");
            for (int j = 0; j < cols; j++)
                Console.Write($"{matrix[i, j],11:0.00E+00} ");
            Console.WriteLine();
        }
        Console.WriteLine();
    }
}