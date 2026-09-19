'use client'

export function TableSkeleton() {
  return (
    <div className="card animate-pulse">
      <div className="overflow-x-auto">
        <table className="table w-full">
          <thead>
            <tr>
              <th className="bg-gray-200 dark:bg-gray-800 h-8 rounded-md mx-2"></th>
              <th className="bg-gray-200 dark:bg-gray-800 h-8 rounded-md mx-2"></th>
              <th className="bg-gray-200 dark:bg-gray-800 h-8 rounded-md mx-2"></th>
              <th className="bg-gray-200 dark:bg-gray-800 h-8 rounded-md mx-2"></th>
              <th className="bg-gray-200 dark:bg-gray-800 h-8 rounded-md mx-2"></th>
            </tr>
          </thead>
          <tbody>
            {[1, 2, 3, 4, 5].map((i) => (
              <tr key={i} className="border-b border-gray-100 dark:border-gray-800">
                <td className="p-4"><div className="h-4 bg-gray-200 dark:bg-gray-800 rounded w-3/4"></div></td>
                <td className="p-4"><div className="h-4 bg-gray-200 dark:bg-gray-800 rounded w-1/2"></div></td>
                <td className="p-4"><div className="h-4 bg-gray-200 dark:bg-gray-800 rounded w-1/4"></div></td>
                <td className="p-4"><div className="h-4 bg-gray-200 dark:bg-gray-800 rounded w-1/3"></div></td>
                <td className="p-4"><div className="h-4 bg-gray-200 dark:bg-gray-800 rounded w-1/2"></div></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
